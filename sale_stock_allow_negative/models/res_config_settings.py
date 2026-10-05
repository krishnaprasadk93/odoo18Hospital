from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_allow_negative_stock = fields.Boolean(
        related='company_id.sale_allow_negative_stock', readonly=False)
