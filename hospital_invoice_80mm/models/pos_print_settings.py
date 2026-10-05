from odoo import models, fields


class PosPrintSettings(models.Model):
    _name = 'pos.print.settings'
    _description = 'POS Thermal Printer Settings'

    name = fields.Char(default="Default Printer Config")

    printer_name = fields.Char(string="Printer Name", required=True)
    auto_print = fields.Boolean(string="Enable Direct Printing", default=True)

    bold_font = fields.Boolean(string="Use Bold Font", default=True)
    double_font = fields.Boolean(string="Use Double Size Font", default=False)

    active = fields.Boolean(default=True)
