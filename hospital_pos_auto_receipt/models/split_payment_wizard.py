from odoo import models, fields, api
from odoo.exceptions import UserError


class SplitPaymentWizard(models.TransientModel):
    _name = 'split.payment.wizard'

    sale_id = fields.Many2one('sale.order', required=True)

    currency_id = fields.Many2one(
        'res.currency',
        related='sale_id.currency_id',
        readonly=True
    )

    amount_total = fields.Monetary(
        currency_field='currency_id',
        readonly=True
    )

    cash_journal_id = fields.Many2one('account.journal', domain="[('type','=','cash')]")
    card_journal_id = fields.Many2one('account.journal', domain="[('type','=','bank')]")
    upi_journal_id = fields.Many2one('account.journal', domain="[('type','=','bank')]")

    cash_amount = fields.Float()
    card_amount = fields.Float()
    upi_amount = fields.Float()

    amount_given = fields.Float(
        string='Amount Given by Customer',
        help='Cash amount physically handed over by the customer.'
    )
    balance_amount = fields.Float(
        string='Balance / Change to Return',
        compute='_compute_balance_amount',
        store=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sale = self.env['sale.order'].browse(self.env.context.get('active_id'))
        res.update({'sale_id': sale.id,'amount_total': sale.amount_total,'cash_amount': sale.amount_total})
        if 'amount_given' in fields_list:
            res['amount_given'] = res.get('cash_amount', 0.0)
        return res

    @api.onchange('card_amount', 'upi_amount')
    def _onchange_split_amounts(self):
        for rec in self:
            other = (rec.card_amount or 0) + (rec.upi_amount or 0)
            rec.cash_amount = rec.amount_total - other

            # Prevent negative cash
            if rec.cash_amount < 0:
                rec.cash_amount = 0

            # Keep "Amount Given" defaulted to the (recomputed) cash portion
            # so a mixed cash+card/upi split still reflects only the cash
            # actually due (the cashier can still edit it afterwards).
            rec.amount_given = rec.cash_amount

    @api.depends('amount_given', 'cash_amount')
    def _compute_balance_amount(self):
        for rec in self:
            rec.balance_amount = (rec.amount_given or 0.0) - (rec.cash_amount or 0.0)

    @api.onchange('amount_given', 'cash_amount')
    def _onchange_amount_given(self):
        for rec in self:
            rec.balance_amount = (rec.amount_given or 0.0) - (rec.cash_amount or 0.0)

    def _check_amount_collected_required(self):
        require_amount_collected = self.env['ir.config_parameter'].sudo().get_param(
            'hospital.require_amount_collected_entry', 'False'
        )
        if str(require_amount_collected).lower() == 'true' and self.cash_amount > 0 and not self.amount_given:
            raise UserError("Please enter the Amount Given by Customer before processing a cash payment.")

    def action_create_invoice_payment1(self):
        self.ensure_one()
        sale = self.sale_id
        self._check_amount_collected_required()

        # 1️⃣ Confirm Sale (triggers your override logic)
        if sale.state not in ['sale', 'done']:
            sale.action_confirm()

        # 2️⃣ Get invoice created by confirm
        invoice = sale.invoice_ids.filtered(lambda m: m.state in ['draft', 'posted'])

        if not invoice:
            raise UserError("Invoice not created.")

        invoice = invoice[0]

        # 3️⃣ Post invoice if still draft
        if invoice.state == 'draft':
            invoice.action_post()

        # 4️⃣ Validate payment amount
        total_paid = self.cash_amount + self.card_amount + self.upi_amount
        if total_paid <= 0:
            raise UserError("Enter payment amount.")

        if total_paid > invoice.amount_residual:
            raise UserError("Payment exceeds balance.")

        # 5️⃣ Register payments
        if self.cash_amount > 0:
            self._register_payment(invoice, self.cash_journal_id, self.cash_amount)

        if self.card_amount > 0:
            self._register_payment(invoice, self.card_journal_id, self.card_amount)

        if self.upi_amount > 0:
            self._register_payment(invoice, self.upi_journal_id, self.upi_amount)

        amount_given = self.amount_given or 0.0
        balance_amount = self.balance_amount
        is_cash_payment = bool(self.cash_amount) and not self.card_amount and not self.upi_amount
        invoice.write({
            'amount_collected': amount_given,
            'balance_amount': balance_amount,
            'is_cash_payment': is_cash_payment,
        })
        sale.write({
            'amount_collected': amount_given,
            'balance_amount': balance_amount,
        })

        if invoice.amount_residual == 0:
            op_ticket = invoice.op_ticket_id or sale.op_ticket_id
            if op_ticket:
                op_ticket.pharmacy_state = 'paid'
                op_ticket.state = 'done'
        # 6️⃣ Print receipt
                # 6️⃣ TRIGGER DIRECT PRINT (Client Action)
                # Check if print method exists (safety check)
                if hasattr(invoice, '_build_escpos_invoice_at301'):
                    escpos_str = invoice._build_escpos_invoice_at301()

                    return {
                        "type": "ir.actions.client",
                        "tag": "hospital_qz_print",  # Calls the JS Action
                        "params": {  # Use params for the custom JS
                            "escpos_raw": escpos_str,
                            "notification": {
                                "type": "success",
                                "title": "Payment Successful",
                                "message": "Invoice created. Printing receipt...",
                                "sticky": False,
                            }
                        },
                    }
                else:
                    # Fallback if print method missing (optional)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Print Error',
                            'message': 'Print method _build_escpos_invoice_at301 not found on invoice.',
                            'type': 'danger',
                        }
                    }

    def action_create_invoice_payment(self):
        self.ensure_one()
        sale = self.sale_id
        self._check_amount_collected_required()

        # 1️⃣ Confirm Sale
        if sale.state not in ['sale', 'done']:
            sale.action_confirm()

        # 2️⃣ Validate Delivery (Auto-assign lot + validate picking)
        pickings = sale.picking_ids.filtered(
            lambda p: p.state not in ['done', 'cancel']
                      and p.picking_type_id.code == 'outgoing'
        )
        for picking in pickings:
            picking.action_assign()  # triggers _action_assign → lot assignment
            # Force immediate transfer without backorder
            picking.with_context(skip_backorder=True, skip_sms=True).button_validate()

        # 3️⃣ Get invoice created by confirm
        # 3️⃣ CREATE Invoice explicitly
        invoice = sale.invoice_ids.filtered(lambda m: m.state in ['draft', 'posted'])
        if not invoice:
            sale._create_invoices()  # ← ADD THIS LINE
            invoice = sale.invoice_ids.filtered(lambda m: m.state in ['draft', 'posted'])

        if not invoice:
            raise UserError("Invoice not created.")
        invoice = invoice[0]
        if invoice.state == 'draft':
            invoice.action_post()
        # 5️⃣ Validate payment amount
        total_paid = self.cash_amount + self.card_amount + self.upi_amount
        if total_paid <= 0:
            raise UserError("Enter payment amount.")
        if total_paid > invoice.amount_residual:
            raise UserError("Payment exceeds balance.")

        # 6️⃣ Register payments
        if self.cash_amount > 0:
            self._register_payment(invoice, self.cash_journal_id, self.cash_amount)
        if self.card_amount > 0:
            self._register_payment(invoice, self.card_journal_id, self.card_amount)
        if self.upi_amount > 0:
            self._register_payment(invoice, self.upi_journal_id, self.upi_amount)

        amount_given = self.amount_given or 0.0
        balance_amount = self.balance_amount
        is_cash_payment = bool(self.cash_amount) and not self.card_amount and not self.upi_amount
        invoice.write({
            'amount_collected': amount_given,
            'balance_amount': balance_amount,
            'is_cash_payment': is_cash_payment,
        })
        sale.write({
            'amount_collected': amount_given,
            'balance_amount': balance_amount,
        })

        if invoice.amount_residual == 0:
            op_ticket = invoice.op_ticket_id or sale.op_ticket_id
            if op_ticket:
                op_ticket.pharmacy_state = 'paid'
                op_ticket.state = 'done'

        # 7️⃣ Print receipt
        if hasattr(invoice, '_build_escpos_invoice_at301'):
            escpos_str = invoice._build_escpos_invoice_at301()
            return {
                "type": "ir.actions.client",
                "tag": "hospital_qz_print",
                "params": {
                    "escpos_raw": escpos_str,
                    "notification": {
                        "type": "success",
                        "title": "Payment Successful",
                        "message": "Invoice created. Printing receipt...",
                        "sticky": False,
                    },
                },
            }

    def _register_payment(self, invoice, journal, amount):
        if not journal or amount <= 0:
            return
        self.env['account.payment.register'].with_context(active_model='account.move',active_ids=invoice.ids).create({'journal_id': journal.id,'amount': amount}).action_create_payments()
