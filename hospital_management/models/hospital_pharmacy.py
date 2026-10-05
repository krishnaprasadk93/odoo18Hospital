from odoo import models, fields, api, _


class HospitalPharmacy(models.Model):
    _name = 'hospital.pharmacy'
    _description = 'Hospital Pharmacy'
    _rec_name = 'name'

    name = fields.Char(string='Pharmacy Name', required=True)
    code = fields.Char(string='Code')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)
    incharge_id = fields.Many2one('hr.employee', string='Pharmacist In-Charge',
                                  domain=[('job_id.name', '=', 'Pharmacist')])
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    address = fields.Text(string='Address')
    active = fields.Boolean(default=True)
