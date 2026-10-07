from datetime import timedelta, datetime, time

import pytz

from odoo import models, fields, api, _, exceptions
from odoo.exceptions import UserError


class HospitalOpTicket(models.Model):
    _name = 'hospital.op.ticket'
    _description = 'Out Patient Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'visit_no'

    token_number = fields.Char(string='Token No', readonly=True, copy=False)
    visit_no = fields.Char(string='Visit No', readonly=True, default='New', copy=False)

    patient_id = fields.Many2one(
        'hospital.patient',
        string='Patient',
        required=True,
        tracking=True,
        options="{'no_create_edit': False}"
    )
    doctor_id = fields.Many2one('hr.employee', string='Doctor', domain=[('job_id.name', '=', 'Doctor')], required=True,
                                tracking=True)

    appointment_date = fields.Datetime(string='Appointment Date', default=fields.Datetime.now)
    patient_type = fields.Selection([('outpatient', 'Out Patient'), ('inpatient', 'In Patient')],
                                    string='Patient Type', default='outpatient', required=True)
    visit_mode = fields.Selection([
        ('offline', 'Offline'),
        ('online', 'Online'),
    ], string='Visit Mode', default='offline', required=True, tracking=True)

    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Pricelist',
        compute='_compute_pricelist_by_mode',
        store=False,
    )
    reason = fields.Text(string='Reason for Visit')

    consultation_product_id = fields.Many2one(
        'product.product',
        string='Consultation Service',
        domain=[('type', '=', 'service')],
        default=lambda self: self.env['product.product'].search([
            ('type', '=', 'service'),
            ('name', 'ilike', 'consultation'),
        ], limit=1)
    )
    consultation_fee = fields.Float(string='Consultation Fee', tracking=True)

    prescription_ids = fields.One2many('prescription.line', 'op_ticket_id', string='Prescription')
    prescription_note = fields.Html(string='General Prescription Notes')
    procedure_line_ids = fields.One2many(
        'op.procedure.line',
        'op_ticket_id',
        string="Procedures"
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('op', 'OP Generated'),
        ('consulting', 'Consulting'),
        ('pharmacy', 'Pharmacy'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True, required=True, group_expand='_expand_states')

    draft_state = fields.Selection([
        ('new', 'New'),
        ('invoiced', 'Invoice Created'),
        ('paid', 'Paid'),
        ('skipped', 'Payment Skipped'),
        ('cancelled', 'Cancelled')
    ], string='Draft Sub-state', default='new', tracking=True)

    consulting_state = fields.Selection([
        ('started', 'Started'),
        ('completed', 'Completed')
    ], string='Consultation Sub-state', tracking=True)

    pharmacy_state = fields.Selection([
        ('pending', 'Pending'),
        ('invoiced', 'Invoiced'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], string='Pharmacy Sub-state', tracking=True)

    invoice_ids = fields.One2many('account.move', 'op_ticket_id', string='Invoices')
    invoice_count = fields.Integer(string='Invoice Count', compute='_compute_invoice_count')

    sale_order_ids = fields.One2many('sale.order', 'op_ticket_id', string='Sale Orders')
    sale_order_count = fields.Integer(string='Sale Order Count', compute='_compute_sale_order_count')

    consultation_invoice_id = fields.Many2one('account.move', string='Consultation Invoice')

    amount_collected = fields.Float(
        string='Amount Collected',
        tracking=True,
        help='Total cash physically handed over by the patient for the consultation payment.'
    )
    balance_amount = fields.Float(
        string='Balance Returned',
        tracking=True,
        help='Change returned to the patient (Amount Collected - Cash Amount).'
    )
    pharmacy_sale_id = fields.Many2one('sale.order', string='Pharmacy Sale Order')
    pharmacy_invoice_id = fields.Many2one('account.move', string='Pharmacy Invoice')

    attachment_id = fields.Many2one('ir.attachment', string='Attachment')
    last_visit_date = fields.Datetime(
        string="Last Visit",
        compute="_compute_last_visit",
        store=False
    )

    last_visit_days = fields.Integer(
        string="Last Visit (Days)",
        compute="_compute_last_visit",
        store=False
    )

    is_free_revisit = fields.Boolean(
        string="Free Revisit",
        compute="_compute_last_visit",
        store=False
    )
    last_visit_text = fields.Char(string="Last Visit Summary", compute="_compute_last_visit_text")

    # Display helpers for the visit header, lists and the queue board.
    patient_name = fields.Char(related='patient_id.name', string='Patient Name')
    patient_summary = fields.Char(string='Patient Details', compute='_compute_patient_summary')
    doctor_name = fields.Char(related='doctor_id.name', string='Doctor Name')
    appointment_time_text = fields.Char(string='Time', compute='_compute_appointment_time_text')
    waiting_text = fields.Char(string='Waiting', compute='_compute_waiting_text')
    prescription_count = fields.Integer(string='Medicines', compute='_compute_pharmacy_status')
    pharmacy_stock_status = fields.Selection([
        ('ready', 'Ready'),
        ('low', 'Low stock'),
        ('none', 'No medicines'),
    ], string='Stock', compute='_compute_pharmacy_status')

    # hospital.op.ticket model
    has_previous_prescription = fields.Boolean(
        string='Has Previous Prescription',
        compute='_compute_has_previous_prescription'
    )

    @api.depends('patient_id')
    def _compute_has_previous_prescription(self):
        for rec in self:
            if rec.patient_id:
                rec.has_previous_prescription = self.env['hospital.op.ticket'].search_count([
                    ('patient_id', '=', rec.patient_id.id),
                    ('id', '!=', rec.id),
                    ('prescription_ids', '!=', False),
                ]) > 0
            else:
                rec.has_previous_prescription = False

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    @api.depends('sale_order_ids')
    def _compute_sale_order_count(self):
        for rec in self:
            rec.sale_order_count = len(rec.sale_order_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('visit_no', 'New') == 'New':
                vals['visit_no'] = self.env['ir.sequence'].next_by_code('hospital.visit') or 'New'
        return super().create(vals_list)

    def _get_default_consultation_product(self):
        return self.env['product.product'].search([
            ('type', '=', 'service'),
            ('name', 'ilike', 'consultation'),
        ], limit=1)

    def _compute_consultation_fee_value(self):
        """Compute the consultation fee for the current visit_mode/pricelist.

        Shared by the form-only onchange and action_refresh_consultation_fee
        (called via RPC by non-UI clients, which never receive onchange
        triggers) so both stay in sync with a single pricing implementation.
        """
        self.ensure_one()
        # Free revisit takes top priority
        if self.is_free_revisit:
            return 0

        ICP = self.env['ir.config_parameter'].sudo()
        if self.visit_mode == 'online':
            pl_id = int(ICP.get_param('hospital.pricelist_online_id', 0))
        else:
            pl_id = int(ICP.get_param('hospital.pricelist_offline_id', 0))

        if pl_id:
            pricelist = self.env['product.pricelist'].browse(pl_id).exists()
            if pricelist:
                # Odoo 18 correct API
                price_rules = pricelist._compute_price_rule(
                    products=self.consultation_product_id,
                    quantity=1.0,
                    currency=None,
                    date=fields.Date.today(),
                )
                price = price_rules.get(
                    self.consultation_product_id.id,
                    (self.consultation_product_id.list_price,)
                )[0]
                return price

        # Fallback: product list price if no pricelist configured
        return self.consultation_product_id.list_price

    @api.onchange('consultation_product_id', 'patient_id', 'visit_mode', 'doctor_id')
    def _onchange_consultation_product(self):
        if not self.consultation_product_id:
            default_product = self._get_default_consultation_product()
            if default_product:
                self.consultation_product_id = default_product

        if self.is_free_revisit:
            self.consultation_fee = 0
            return

        if not self.consultation_product_id:
            return

        self.consultation_fee = self._compute_consultation_fee_value()

    def action_refresh_consultation_fee(self):
        """RPC-callable equivalent of _onchange_consultation_product.

        Non-UI clients (e.g. the mobile/web apps talking to Odoo over
        JSON-RPC) never trigger onchange handlers, so consultation_fee
        would otherwise stay 0 after a plain `create`. Call this right
        after creating/updating a ticket, then re-read consultation_fee.
        """
        for rec in self:
            if not rec.consultation_product_id:
                default_product = rec._get_default_consultation_product()
                if default_product:
                    rec.consultation_product_id = default_product
            if rec.consultation_product_id:
                rec.consultation_fee = rec._compute_consultation_fee_value()
        return True

    def action_create_consultation_invoice_old(self):
        self.ensure_one()
        if not self.consultation_product_id:
            raise exceptions.UserError(_('Please select a consultation service product.'))

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.patient_id.partner_id.id,
            'invoice_date': fields.Date.today(),
            'op_ticket_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.consultation_product_id.id,
                'name': f'Consultation - Dr. {self.doctor_id.name}',
                'quantity': 1,
                'price_unit': self.consultation_fee,
                'tax_ids': [(6, 0, self.consultation_product_id.taxes_id.ids)],
            })]
        }

        invoice = self.env['account.move'].create(invoice_vals)
        self.write({
            'consultation_invoice_id': invoice.id,
            'draft_state': 'invoiced'
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_consultation_invoice(self):
        self.ensure_one()
        if not self.consultation_product_id:
            raise exceptions.UserError(_('Please select a consultation service product.'))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Split Payment & Invoice',
            'res_model': 'consultation.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op_ticket_id': self.id,
                'default_amount_cash': self.consultation_fee,  # Default to full cash
            }
        }

    def action_register_payment(self):
        self.ensure_one()
        if not self.consultation_invoice_id:
            raise exceptions.UserError(_('Please create an invoice first.'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': self.consultation_invoice_id.ids,
            }
        }

    def action_skip_payment(self):
        self.draft_state = 'skipped'

    def _get_doctor_token(self, doctor_id):
        today = fields.Date.today()

        # Count existing tokens for doctor today
        count = self.search_count([
            ('doctor_id', '=', doctor_id.id),
            ('appointment_date', '>=', fields.Datetime.to_datetime(today)),
            ('appointment_date', '<', fields.Datetime.to_datetime(today) + timedelta(days=1)),
            ('token_number', '!=', False),
        ])

        return str(count + 1).zfill(3)

    def action_generate_token(self):
        self.ensure_one()
        if self.draft_state not in ['paid', 'skipped']:
            raise exceptions.UserError(_('Please complete payment or skip payment first.'))

        if not self.token_number:
            seq = self._get_doctor_token(self.doctor_id)
            self.write({'token_number': seq, 'state': 'consulting', 'consulting_state': 'started'})

    def action_cancel_draft(self):
        self.write({'state': 'cancelled', 'draft_state': 'cancelled'})

    def action_start_consult(self):
        self.write({'state': 'consulting', 'consulting_state': 'started'})

    def action_complete_consult(self):
        self.consulting_state = 'completed'
        '''if not self.prescription_ids:
            raise exceptions.UserError(_('Please add prescriptions before sending to pharmacy.'))'''
        self.write({'state': 'pharmacy', 'pharmacy_state': 'pending'})

    def action_send_to_pharmacy(self):
        '''if not self.prescription_ids:
            raise exceptions.UserError(_('Please add prescriptions before sending to pharmacy.'))'''
        self.write({'state': 'pharmacy', 'pharmacy_state': 'pending'})

    def action_skip_pharmacy(self):
        self.state = 'done'

    def action_create_pharmacy_sale(self):
        self.ensure_one()

        if not self.prescription_ids and not self.procedure_line_ids:
            raise exceptions.UserError(
                _('Please add at least one Prescription or Procedure before sending to pharmacy.')
            )

        today = fields.Date.today()

        sale_vals = {
            'partner_id': self.patient_id.partner_id.id,
            'date_order': fields.Datetime.now(),
            'op_ticket_id': self.id,
            'order_line': []
        }

        # ==================================
        # MEDICINES (AUTO FEFO SAFE VERSION)
        # ==================================
        for line in self.prescription_ids:

            product = line.medicine_id
            required_qty = line.quantity
            assigned_qty = 0

            # -------- STEP 1: NON-EXPIRED LOTS --------
            quant_data = self.env['stock.quant'].read_group(
                domain=[
                    ('product_id', '=', product.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0),
                    ('lot_id.expiration_date', '>=', today),
                ],
                fields=['quantity:sum', 'lot_id'],
                groupby=['lot_id'],
            )

            # -------- STEP 2: FALLBACK TO ANY LOT --------
            if not quant_data:
                quant_data = self.env['stock.quant'].read_group(
                    domain=[
                        ('product_id', '=', product.id),
                        ('location_id.usage', '=', 'internal'),
                        ('quantity', '>', 0),
                    ],
                    fields=['quantity:sum', 'lot_id'],
                    groupby=['lot_id'],
                )

            # -------- STEP 3: NO STOCK --------
            if not quant_data:
                raise UserError(
                    f"No stock available for {product.display_name}"
                )

            # -------- STEP 4: BUILD LOT LIST --------
            lot_data = []
            for data in quant_data:
                if not data['lot_id']:
                    continue

                lot = self.env['stock.lot'].browse(data['lot_id'][0])

                lot_data.append({
                    'lot': lot,
                    'qty': data['quantity'],
                    'expiry': lot.expiration_date or datetime.max
                })

            # -------- STEP 5: FEFO SORT --------
            lot_data = sorted(lot_data, key=lambda x: x['expiry'])

            # -------- STEP 6: SPLIT QUANTITY --------
            for item in lot_data:
                lot = item['lot']
                lot_qty = item['qty']

                take_qty = min(required_qty - assigned_qty, lot_qty)

                sale_vals['order_line'].append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': take_qty,
                    'price_unit': lot.selling_price or product.list_price,
                    'tax_id': [(6, 0, product.taxes_id.ids)],
                    'lot_id': lot.id,
                }))

                assigned_qty += take_qty

                if assigned_qty >= required_qty:
                    break

            if assigned_qty < required_qty:
                raise UserError(
                    f"Not enough stock for {product.display_name}"
                )

        # ===========================
        # PROCEDURES (NORMAL)
        # ===========================
        for line in self.procedure_line_ids:
            sale_vals['order_line'].append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'price_unit': line.price_unit,
                'name': line.product_id.name,
            }))

        sale_order = self.env['sale.order'].create(sale_vals)

        self.write({'pharmacy_sale_id': sale_order.id})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_pharmacy_invoice(self):
        self.ensure_one()
        if not self.pharmacy_sale_id:
            raise exceptions.UserError(_('Please create a sale order first.'))

        invoice = self.pharmacy_sale_id._create_invoices()

        if invoice:
            invoice.write({'op_ticket_id': self.id})
            self.write({'pharmacy_invoice_id': invoice.id, 'pharmacy_state': 'invoiced'})

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': invoice.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_register_pharmacy_payment(self):
        self.ensure_one()
        if not self.pharmacy_invoice_id:
            raise exceptions.UserError(_('Please create pharmacy invoice first.'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': self.pharmacy_invoice_id.ids,
            }
        }

    def action_pharmacy_done(self):
        self.write({'state': 'done', 'pharmacy_state': 'paid'})

    def action_cancel_pharmacy(self):
        # self.pharmacy_state = 'cancelled'
        self.write({'state': 'done'})

    def action_view_invoices(self):
        return {
            'name': _('Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }

    def action_view_sale_orders(self):
        return {
            'name': _('Sale Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sale_order_ids.ids)],
        }

    @api.model
    def _reset_daily_token_sequence(self):
        sequence = self.env['ir.sequence'].search([('code', '=', 'hospital.op.token')], limit=1)
        if sequence:
            sequence.write({'number_next_actual': 1})

    @api.model
    def _update_payment_states(self):
        draft_tickets = self.search([('state', '=', 'draft'), ('draft_state', '=', 'invoiced')])
        for ticket in draft_tickets:
            if ticket.consultation_invoice_id.payment_state == 'paid':
                ticket.draft_state = 'paid'

        pharmacy_tickets = self.search([('state', '=', 'pharmacy'), ('pharmacy_state', '=', 'invoiced')])
        for ticket in pharmacy_tickets:
            if ticket.pharmacy_invoice_id.payment_state == 'paid':
                ticket.pharmacy_state = 'paid'

    @api.depends('patient_id', 'doctor_id')
    def _compute_last_visit(self):
        for rec in self:
            rec.last_visit_date = False
            rec.last_visit_days = 0
            rec.is_free_revisit = False
            if not rec.patient_id:
                continue

            check_type = self.env['ir.config_parameter'].sudo().get_param(
                'hospital.revisit_check_type', default='hospital'
            )
            domain = [
                ('patient_id', '=', rec.patient_id.id),
                ('id', '!=', rec.id),
                ('state', 'in', ['done', 'consulting', 'pharmacy']),
                ('consultation_invoice_id', '!=', False),  # only invoiced visits
            ]
            if check_type == 'doctor' and rec.doctor_id:
                domain.append(('doctor_id', '=', rec.doctor_id.id))

            candidate_tickets = self.env['hospital.op.ticket'].search(domain)

            # Pick the ticket with the most recent consultation invoice_date
            last_ticket = max(
                candidate_tickets.filtered(
                    lambda t: t.consultation_invoice_id
                              and t.consultation_invoice_id.invoice_date
                ),
                key=lambda t: t.consultation_invoice_id.invoice_date,
                default=None
            )

            if last_ticket:
                invoice_date = last_ticket.consultation_invoice_id.invoice_date
                rec.last_visit_date = datetime.combine(invoice_date, time.min)
                current_date = rec.appointment_date.date() if rec.appointment_date else fields.Date.today()
                delta = current_date - invoice_date
                rec.last_visit_days = delta.days
                limit_days = int(self.env['ir.config_parameter'].sudo().get_param(
                    'hospital.revisit_limit_days', default=15
                ))
                if delta.days < limit_days:
                    rec.is_free_revisit = True

    @api.depends('last_visit_date', 'last_visit_days', 'is_free_revisit')
    def _compute_last_visit_text(self):
        for rec in self:
            if not rec.last_visit_date:
                rec.last_visit_text = False
                continue
            days = rec.last_visit_days
            when = _('today') if days <= 0 else (_('yesterday') if days == 1 else _('%s days ago', days))
            text = _('Last visit %s', when)
            if rec.is_free_revisit:
                text += ' · ' + _('Free revisit')
            rec.last_visit_text = text

    @api.depends('patient_id.age', 'patient_id.gender', 'patient_id.blood_group', 'patient_id.rh_type')
    def _compute_patient_summary(self):
        for rec in self:
            rec.patient_summary = rec.patient_id._get_profile_summary() if rec.patient_id else False

    @api.depends('appointment_date')
    @api.depends_context('tz')
    def _compute_appointment_time_text(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.appointment_date:
                rec.appointment_time_text = False
                continue
            local = fields.Datetime.context_timestamp(rec, rec.appointment_date)
            if local.date() == today:
                fmt = '%I:%M %p'
            elif local.year == today.year:
                fmt = '%d %b, %I:%M %p'
            else:
                fmt = '%d %b %Y, %I:%M %p'
            rec.appointment_time_text = local.strftime(fmt)

    def _compute_waiting_text(self):
        """ Time since the appointment for visits still in the clinic (today only). """
        now = fields.Datetime.now()
        for rec in self:
            rec.waiting_text = False
            if rec.state not in ('op', 'consulting', 'pharmacy') or not rec.appointment_date:
                continue
            minutes = int((now - rec.appointment_date).total_seconds() // 60)
            if minutes < 1 or minutes >= 24 * 60:
                continue
            hours, mins = divmod(minutes, 60)
            rec.waiting_text = _('%(h)s h %(m)s min', h=hours, m=mins) if hours else _('%s min', mins)

    @api.depends('prescription_ids', 'prescription_ids.is_out_of_stock')
    def _compute_pharmacy_status(self):
        for rec in self:
            lines = rec.prescription_ids
            rec.prescription_count = len(lines)
            if not lines:
                rec.pharmacy_stock_status = 'none'
            elif any(lines.mapped('is_out_of_stock')):
                rec.pharmacy_stock_status = 'low'
            else:
                rec.pharmacy_stock_status = 'ready'

    @api.model
    def get_clinic_home_data(self):
        """ Live counts for the Clinic home tiles, limited to the menus the user can open. """
        user = self.env.user
        tz_today = fields.Date.context_today(self)
        start = fields.Datetime.context_timestamp(self, fields.Datetime.now()).replace(
            hour=0, minute=0, second=0, microsecond=0)
        start_utc = start.astimezone(pytz.utc).replace(tzinfo=None)
        today = [('appointment_date', '>=', start_utc),
                 ('appointment_date', '<', start_utc + timedelta(days=1))]
        active = [('state', 'not in', ('done', 'cancelled'))]
        tiles = []
        if user.has_group('hospital_management.group_hospital_receptionist'):
            tiles += [
                {'key': 'queue', 'label': _("Today's Queue"), 'icon': 'fa-th-large',
                 'count': self.search_count(today + active),
                 'hint': _('in the clinic now · %s visits today',
                           self.search_count(today + [('state', '!=', 'cancelled')])),
                 'action': 'hospital_management.action_reception_queue'},
                {'key': 'register', 'label': _('Register Patient'), 'icon': 'fa-user-plus',
                 'count': self.env['hospital.patient'].search_count([('create_date', '>=', start_utc)]),
                 'hint': _('new patients today'),
                 'action': 'hospital_management.action_hospital_patient', 'new': True},
            ]
        if user.has_group('hospital_management.group_hospital_doctor'):
            mine = [('doctor_id.user_id', '=', user.id)]
            tiles.append({
                'key': 'my_queue', 'label': _('My Queue'), 'icon': 'fa-stethoscope',
                'count': self.search_count(today + mine + [('state', 'in', ('op', 'consulting'))]),
                'hint': _('waiting or in consultation'),
                'action': 'hospital_management.action_doctor_queue'})
        if user.has_group('hospital_management.group_hospital_pharmacist'):
            tiles.append({
                'key': 'pharmacy', 'label': _('Pharmacy Queue'), 'icon': 'fa-medkit',
                'count': self.search_count([('state', '=', 'pharmacy')]),
                'hint': _('prescriptions to dispense'),
                'action': 'hospital_management.action_pharmacy_dashboard'})
            low = self.env['product.product'].search_count(
                [('is_medicine', '=', True), ('stock_level', 'in', ['out', 'low'])])
            tiles.append({
                'key': 'stock', 'label': _('Low Stock'), 'icon': 'fa-cubes', 'alert': low > 0,
                'count': low, 'hint': _('medicines out of stock or low'),
                'action': 'hospital_management.action_medicine_products',
                'context': {'search_default_filter_low_stock': 1, 'search_default_filter_out_of_stock': 1}})
        return {'tiles': tiles, 'date': fields.Date.to_string(tz_today), 'user': user.name}

    @api.model
    def _expand_states(self, states, domain):
        # Queue board: always show the active stages; cancelled only when it has visits.
        keys = [key for key, _label in self._fields['state'].selection if key != 'cancelled']
        return keys + (['cancelled'] if 'cancelled' in states else [])

    def action_view_visits2(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Patient Visits',
            'res_model': 'hospital.op.ticket',
            'view_mode': 'list',  # list only, no form switching needed
            'views': [(False, 'list')],
            'domain': [
                ('patient_id', '=', self.patient_id.id),
                ('id', '!=', self.id)
            ],
            'target': 'new',
        }

    def action_open_form_popup(self):
        popup_form_view = self.env.ref(
            'hospital_management.view_op_ticket_popup_form'
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Visit Details',
            'res_model': 'hospital.op.ticket',
            'view_mode': 'form',
            'views': [(popup_form_view.id, 'form')],
            'res_id': self.id,
            'target': 'new',
            'flags': {
                'mode': 'readonly',
                'action_buttons': False,
            },
        }

    def action_view_visits(self):
        popup_list_view = self.env.ref(
            'hospital_management.view_op_ticket_popup_list'
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Patient Visits',
            'res_model': 'hospital.op.ticket',
            'view_mode': 'list',
            'views': [(popup_list_view.id, 'list')],  # use dedicated view
            'domain': [
                ('patient_id', '=', self.patient_id.id),
                ('id', '!=', self.id)
            ],
            'target': 'new',
        }

    def action_copy_last_prescription(self):
        last_visit = self.env['hospital.op.ticket'].search([
            ('patient_id', '=', self.patient_id.id),
            ('id', '!=', self.id),
            ('prescription_ids', '!=', False),
        ], order='appointment_date desc', limit=1)

        if not last_visit:
            raise UserError(_('No previous visit with prescription found for this patient.'))

        new_lines = []
        for line in last_visit.prescription_ids:
            new_lines.append((0, 0, {
                'medicine_id': line.medicine_id.id,
                'morning_dose': line.morning_dose,
                'afternoon_dose': line.afternoon_dose,
                'evening_dose': line.evening_dose,
                'duration_number': line.duration_number,
                'duration_type': line.duration_type,
                'instruction': line.instruction,
                'notes': line.notes,
                'quantity': line.quantity,
            }))

        self.write({'prescription_ids': new_lines})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _(f'Copied {len(new_lines)} prescription(s) from visit {last_visit.visit_no}'),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'soft_reload',
                }
            }
        }

    @api.depends('visit_mode')
    def _compute_pricelist_by_mode(self):
        ICP = self.env['ir.config_parameter'].sudo()
        offline_id = int(ICP.get_param('hospital.pricelist_offline_id', 0))
        online_id = int(ICP.get_param('hospital.pricelist_online_id', 0))
        for rec in self:
            if rec.visit_mode == 'online' and online_id:
                rec.pricelist_id = self.env['product.pricelist'].browse(online_id)
            elif offline_id:
                rec.pricelist_id = self.env['product.pricelist'].browse(offline_id)
            else:
                rec.pricelist_id = False

    def write(self, vals):
        if 'visit_mode' in vals:
            for rec in self:
                if rec.consultation_invoice_id:
                    raise UserError(
                        _('Visit mode cannot be changed after a consultation invoice is created.')
                    )
        return super().write(vals)
