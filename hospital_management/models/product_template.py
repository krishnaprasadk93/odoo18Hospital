from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from .dose_preset import parse_quick_doses


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

    # Optional per-medicine dosing (overrides the preset of the medicine type)
    dose_step = fields.Float(string='+/- Step', digits=(16, 2),
                             help='Leave empty to use the step of the medicine type preset.')
    dose_quick_values = fields.Char(string='Quick Doses',
                                    help='Comma-separated doses shown as chips, e.g. 0.3,0.6,0.9. '
                                         'Leave empty to use the medicine type preset.')
    prescription_required = fields.Boolean(string='Prescription Required', default=True)
    expiry_alert_days = fields.Integer(string='Expiry Alert (Days)', default=90,
                                       help='Alert when medicine expires in X days')

    @api.constrains('dose_step', 'dose_quick_values')
    def _check_dose_settings(self):
        for rec in self:
            if rec.dose_step < 0:
                raise ValidationError(_('The +/- step cannot be negative.'))
            parse_quick_doses(rec.dose_quick_values)

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

