from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ConsultationPaymentWizard(models.TransientModel):
    _name = 'consultation.payment.wizard'
    _description = 'Consultation Split Payment Wizard'

    op_ticket_id = fields.Many2one('hospital.op.ticket', string='Appointment', required=True)
    amount_total = fields.Float(string='Total Amount', related='op_ticket_id.consultation_fee', readonly=True)

    # Split Payment Fields
    journal_cash_id = fields.Many2one('account.journal', string='Cash Journal', domain=[('type', '=', 'cash')],
                                      required=True)
    amount_cash = fields.Float(string='Cash Amount')

    journal_card_id = fields.Many2one('account.journal', string='Card Journal', domain=[('type', '=', 'bank')])
    amount_card = fields.Float(string='Card Amount')

    journal_upi_id = fields.Many2one('account.journal', string='UPI Journal', domain=[('type', '=', 'bank')])
    amount_upi = fields.Float(string='UPI Amount')

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
        if 'amount_given' in fields_list and not res.get('amount_given'):
            res['amount_given'] = res.get('amount_cash', 0.0)
        return res

    @api.depends('amount_given', 'amount_cash')
    def _compute_balance_amount(self):
        for rec in self:
            rec.balance_amount = (rec.amount_given or 0.0) - (rec.amount_cash or 0.0)

    @api.onchange('amount_cash')
    def _onchange_amount_cash(self):
        # Keep "Amount Given" defaulted to the cash portion whenever it
        # changes, so a mixed cash+card/upi split still reflects only the
        # cash actually due (the cashier can still edit it afterwards).
        for rec in self:
            rec.amount_given = rec.amount_cash

    @api.onchange('amount_given', 'amount_cash')
    def _onchange_amount_given(self):
        for rec in self:
            rec.balance_amount = (rec.amount_given or 0.0) - (rec.amount_cash or 0.0)

    @api.constrains('amount_cash', 'amount_card', 'amount_upi')
    def _check_amounts(self):
        for rec in self:
            total_paid = rec.amount_cash + rec.amount_card + rec.amount_upi
            # Allow small float differences
            if abs(total_paid - rec.amount_total) > 0.01:
                raise UserError(_(
                    "Total payment (%.2f) must match Consultation Fee (%.2f)."
                ) % (total_paid, rec.amount_total))

    def action_process_payment(self):
        self.ensure_one()
        ticket = self.op_ticket_id

        require_amount_collected = self.env['ir.config_parameter'].sudo().get_param(
            'hospital.require_amount_collected_entry', 'False'
        )
        if str(require_amount_collected).lower() == 'true' and self.amount_cash > 0 and not self.amount_given:
            raise UserError(_(
                "Please enter the Amount Given by Customer before processing a cash payment."
            ))

        # 1. Create and Post Invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': ticket.patient_id.partner_id.id,
            'invoice_date': fields.Date.today(),
            'op_ticket_id': ticket.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': ticket.consultation_product_id.id,
                'name': f'Consultation - {ticket.doctor_id.name}',
                'quantity': 1,
                'price_unit': ticket.consultation_fee,
            })]
        }
        invoice = self.env['account.move'].create(invoice_vals)
        invoice.action_post()

        # 2. Register Payments Loop
        payments_to_create = [
            (self.journal_cash_id, self.amount_cash),
            (self.journal_card_id, self.amount_card),
            (self.journal_upi_id, self.amount_upi)
        ]

        for journal, amount in payments_to_create:
            if amount > 0 and journal:
                # Create Payment
                payment = self.env['account.payment'].create({
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': ticket.patient_id.partner_id.id,
                    'amount': amount,
                    'journal_id': journal.id,
                    'date': fields.Date.today(),
                    'memo': f'{ticket.visit_no} - {journal.name}',
                })
                payment.action_post()

                # --- FIX STARTS HERE ---
                # Retrieve lines from the linked move_id, NOT payment.line_ids
                if not payment.move_id:
                    continue  # Should not happen if posted correctly

                # Find the receivable line on the PAYMENT side
                # The payment move usually has a Liquidity line (Bank/Cash) and a Counterpart line (Receivable/Payable)
                payment_line = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )

                # Find the receivable line on the INVOICE side
                invoice_line = invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )

                # Reconcile them
                (invoice_line + payment_line).reconcile()
                # --- FIX ENDS HERE ---

        # 3. Update Ticket State
        amount_given = self.amount_given or 0.0
        balance_amount = self.balance_amount
        is_cash_payment = bool(self.amount_cash) and not self.amount_card and not self.amount_upi
        ticket.write({
            'consultation_invoice_id': invoice.id,
            'draft_state': 'paid',
            'amount_collected': amount_given,
            'balance_amount': balance_amount,
        })
        invoice.write({
            'amount_collected': amount_given,
            'balance_amount': balance_amount,
            'is_cash_payment': is_cash_payment,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

