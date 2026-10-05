from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_medicine = fields.Boolean(string='Is Medicine', help='Check if product is a medicine')
    is_procedure = fields.Boolean(string="Is Procedure")
    medicine_brand_id = fields.Many2one('medicine.brand', string='Medicine Brand')
    generic_name = fields.Char(string='Generic Name', help='Generic/Scientific name of medicine')
    dosage = fields.Char(string='Dosage', help='e.g., 500mg, 10ml')
    medicine_type = fields.Selection([
        ('tablet', 'Tablet'),
        ('capsule', 'Capsule'),
        ('syrup', 'Syrup'),
        ('kashayam', 'Kashayam'),
        ('drops', 'Drops'),
        ('leham', 'Leham'),
        ('choornam', 'Choornam'),
        ('ointment', 'Ointment'),
        ('oil', 'Oil'),
        ('cream', 'Cream'),
        ('shampoo', 'Shampoo'),
        ('powder', 'Powder'),
        ('serum', 'Serum'),
        ('lotion', 'Lotion'),
        ('spray', 'Spray'),
        ('soap', 'Soap'),
        ('linament', 'Linament'),
        ('other', 'Other')
    ], string='Medicine Type')

    prescription_required = fields.Boolean(string='Prescription Required', default=True)
    expiry_alert_days = fields.Integer(string='Expiry Alert (Days)', default=90,
                                       help='Alert when medicine expires in X days')

    @api.model
    def create(self, vals):

        if vals.get('is_medicine'):

            vals['tracking'] = 'lot'
            vals['is_storable'] = True
            vals['type'] = 'consu'  # Storable
            medicine_category = self.env['product.category'].search(
                [('name', '=', 'Medicine')], limit=1
            )

            if not medicine_category:
                medicine_category = self.env['product.category'].create({
                    'name': 'Medicine'
                })

            vals['categ_id'] = medicine_category.id

        return super().create(vals)

    def action_open_medicine_purchase_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Medicine',
            'res_model': 'medicine.purchase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id
            }
        }

