from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    lot_id = fields.Many2one(
        "stock.lot",
        string="Batch No"
    )

    expiry_date = fields.Date(
        compute="_compute_expiry_date",
        store=True
    )

    @api.depends('lot_id')
    def _compute_expiry_date(self):
        for rec in self:
            if rec.lot_id and rec.lot_id.expiration_date:
                rec.expiry_date = rec.lot_id.expiration_date.date()
            else:
                rec.expiry_date = False

    expiry_mm_yy = fields.Char(
        string="Expiry (MM/YY)",
        compute="_compute_expiry_mm_yy",
        store=False
    )

    @api.depends('expiry_date')
    def _compute_expiry_mm_yy(self):
        for rec in self:
            if rec.expiry_date:
                rec.expiry_mm_yy = rec.expiry_date.strftime("%m/%y")
            else:
                rec.expiry_mm_yy = ""
