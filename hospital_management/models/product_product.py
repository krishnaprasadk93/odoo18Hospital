from odoo import models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

    def action_open_medicine_purchase_wizard(self):
        self.ensure_one()

        # Optional safety check
        if not self.product_tmpl_id.is_medicine:
            raise UserError("This product is not marked as Medicine.")

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
