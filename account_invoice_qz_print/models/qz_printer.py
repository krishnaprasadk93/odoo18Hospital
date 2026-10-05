# models/qz_printer.py
from odoo import api, fields, models


class QzPrinter(models.Model):
    _name = "qz.printer"
    _description = "QZ Tray Printer"

    name = fields.Char("Printer Name", required=True)
    is_default = fields.Boolean("Default Printer")
    paper_width_mm = fields.Integer("Paper Width (mm)", default=80)
    active = fields.Boolean(default=True)

    @api.constrains("is_default")
    def _check_only_one_default(self):
        for rec in self:
            if rec.is_default:
                others = self.search([
                    ("id", "!=", rec.id),
                    ("is_default", "=", True),
                ])
                others.write({"is_default": False})
