from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    show_print_preview = fields.Boolean(
        string='Show Print Preview',
        config_parameter='hospital_print_preview.show_print_preview',
        help='When enabled, thermal receipts (consultation, pharmacy, invoice) '
             'open a print preview with a Print button instead of printing '
             'directly to QZ Tray.'
    )
