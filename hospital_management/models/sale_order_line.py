from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Batch No',
        domain="[('product_id','=',product_id)]"
    )

    expiry_date = fields.Datetime(
        related='lot_id.expiration_date',
        string='Expiry',
        readonly=True
    )
    expiry_date_only = fields.Date(
        string="Expiry Date",
        compute="_compute_expiry_date_only",
        store=False
    )

    def _compute_expiry_date_only(self):
        for rec in self:
            if rec.expiry_date:
                rec.expiry_date_only = rec.expiry_date.date()
            else:
                rec.expiry_date_only = False

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id:
            # Update price from batch
            self.price_unit = self.lot_id.selling_price or self.product_id.list_price

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)

        # Copy lot_id to invoice line
        if self.lot_id:
            res.update({
                'lot_id': self.lot_id.id,
            })

        return res