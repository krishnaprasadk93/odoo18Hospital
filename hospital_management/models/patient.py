from odoo import models, fields, api, _
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo.exceptions import ValidationError


class HospitalPatient(models.Model):
    _name = 'hospital.patient'
    _description = 'Hospital Patient'
    _inherits = {'res.partner': 'partner_id'}
    _rec_name = 'display_name'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')

    patient_seq = fields.Char(string='Patient ID', copy=False, readonly=True, index=True, default=lambda self: 'New')
    barcode = fields.Char(string='Barcode')
    barcode_png = fields.Binary(string='Barcode PNG', readonly=True)

    date_of_birth = fields.Date(string='Date of Birth')
    age = fields.Integer(
        string='Age',
        compute='_compute_age',
        inverse='_inverse_age',
        store=True
    )
    blood_group = fields.Selection([('a', 'A'), ('b', 'B'), ('o', 'O'), ('ab', 'AB')], string='Blood Group')
    rh_type = fields.Selection([('+', '+ve'), ('-', '-ve')], string='RH Type')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], string='Gender')
    marital_status = fields.Selection([
        ('married', 'Married'), ('unmarried', 'Unmarried'),
        ('widow', 'Widow'), ('widower', 'Widower'), ('divorcee', 'Divorcee')
    ], string='Marital Status')

    economic_level = fields.Selection([('low', 'Lower Class'), ('middle', 'Middle Class'), ('upper', 'Upper Class')],
                                      string="Socioeconomic")
    education_level = fields.Selection(
        [('post', 'Post Graduation'), ('graduation', 'Graduation'), ('pre', 'Pre Graduation')],
        string="Education Level")
    occupation = fields.Char(string='Occupation')
    income = fields.Monetary(string='Income')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    exercise = fields.Boolean(string='Exercise')
    sleep_hrs = fields.Integer(string='Sleep Hours')
    smoker = fields.Boolean(string='Smoker')
    drinker = fields.Boolean(string='Drinker')
    diet = fields.Boolean(string='Currently On Diet')
    alcoholic = fields.Boolean(string='Alcoholic')

    house_level = fields.Selection([('good', 'Good'), ('bad', 'Bad'), ('poor', 'Poor')], string="House Condition")
    work_home = fields.Boolean(string='Work At Home')
    internet = fields.Boolean(string='Internet')
    home_phone = fields.Boolean(string='Telephone')

    fertile = fields.Boolean(string='Fertile')
    menarche_age = fields.Integer(string='Menarche Age')
    pause = fields.Boolean(string='Menopause')
    mammography = fields.Boolean(string='Mammography')
    pap = fields.Boolean(string='PAP Test')

    doctor_id = fields.Many2one('hr.employee', string="Family Doctor")
    insurance_id = fields.Many2one('res.partner', string="Insurance Provider")
    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True
    )
    visit_count = fields.Integer(compute="_compute_visit_count")

    visit_ids = fields.One2many('hospital.op.ticket', 'patient_id', string='Visit History')
    sql_constraints = [
        ('patient_seq_unique', 'unique(patient_seq)', 'Patient ID must be unique!')
    ]

    def name_get(self):
        result = []
        for rec in self:
            patient_no = rec.patient_seq or ''
            name = rec.partner_id.name or ''
            phone = rec.partner_id.phone or rec.partner_id.mobile or ''
            display_name = f"[{patient_no}] {name} - {phone}"
            result.append((rec.id, display_name))
        return result

    def _compute_visit_count(self):
        for rec in self:
            rec.visit_count = self.env['hospital.op.ticket'].search_count([
                ('patient_id', '=', rec.id)
            ])

    @api.depends('patient_seq', 'partner_id.name', 'partner_id.phone', 'partner_id.mobile')
    def _compute_display_name(self):
        for rec in self:
            name = rec.partner_id.name or ''
            phone = rec.partner_id.phone or rec.partner_id.mobile or ''
            rec.display_name = f"[{rec.patient_seq}] {name} - {phone}"

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []

        if name:
            args = ['|', '|',
                    ('patient_seq', operator, name),
                    ('partner_id.name', operator, name),
                    ('partner_id.phone', operator, name)
                    ] + args

        patients = self.search(args, limit=limit)
        return patients.name_get()

    @api.depends('date_of_birth')
    def _compute_age(self):
        for rec in self:
            if rec.date_of_birth:
                today = fields.Date.today()
                rec.age = relativedelta(today, rec.date_of_birth).years
            else:
                rec.age = 0

    def _inverse_age(self):
        for rec in self:
            if rec.age and not rec.date_of_birth:
                today = fields.Date.today()
                rec.date_of_birth = today - relativedelta(years=rec.age)

    @api.onchange('age')
    def _onchange_age(self):
        if self.age and not self.date_of_birth:
            self.date_of_birth = fields.Date.today() - relativedelta(years=self.age)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('patient_seq', 'New') == 'New':
                vals['patient_seq'] = self.env['ir.sequence'].next_by_code('hospital.patient')

            if not vals.get('name'):
                vals['name'] = f"Patient {vals['patient_seq']}"

        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if not rec.partner_id.name:
                rec.partner_id.name = f"Patient {rec.patient_seq}"
        return res

    @api.constrains('partner_id')
    def _check_phone_mandatory(self):
        for rec in self:
            if not rec.partner_id.phone and not rec.partner_id.mobile:
                raise ValidationError("Phone or Mobile number is mandatory for Patient.")

    def action_view_visits(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Patient Visits',
            'res_model': 'hospital.op.ticket',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id}
        }

