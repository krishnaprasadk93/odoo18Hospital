from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sale_allow_negative_stock = fields.Boolean(
        string='Allow Negative Stock on Sales',
        default=True,
        help='Force the availability of delivery orders created from sale '
             'orders, so they are Ready to validate even without stock.',
    )
