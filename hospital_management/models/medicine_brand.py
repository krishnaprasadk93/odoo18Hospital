from odoo import models, fields, api, _


class MedicineBrand(models.Model):
    _name = 'medicine.brand'
    _description = 'Medicine Brand'
    _rec_name = 'name'

    name = fields.Char(string='Brand Name', required=True)
    code = fields.Char(string='Brand Code')
    manufacturer = fields.Char(string='Manufacturer')
    country_id = fields.Many2one('res.country', string='Country of Origin')
    product_ids = fields.One2many('product.template', 'medicine_brand_id', string='Products')
    active = fields.Boolean(default=True)
