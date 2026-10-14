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

    lot_available_qty = fields.Float(related='lot_id.product_qty', string='Batch Stock')

    @api.depends('lot_id.expiration_date')
    def _compute_expiry_date_only(self):
        for rec in self:
            if rec.expiry_date:
                rec.expiry_date_only = rec.expiry_date.date()
            else:
                rec.expiry_date_only = False

    def _hc_default_batch(self):
        """ Batch to pre-fill for this line (FEFO), among batches not expired:
        - the earliest-expiring one with enough stock for the quantity;
        - none when stock exists but no single batch has enough (the delivery
          then splits the quantity across batches);
        - the earliest-expiring one when there is no stock at all (it will
          go negative on delivery). """
        self.ensure_one()
        Lot = self.env['stock.lot']
        product = self.product_id
        if not (product.is_storable and product.tracking != 'none'):
            return Lot
        company = self.order_id.company_id or self.env.company
        domain = [('product_id', '=', product.id), ('company_id', 'in', (False, company.id))]
        order = 'id asc'
        if 'expiration_date' in Lot._fields:
            domain += ['|', ('expiration_date', '=', False), ('expiration_date', '>', fields.Datetime.now())]
            order = 'expiration_date asc, id asc'
        lots = Lot.search(domain, order=order)
        stocked = lots.filtered(lambda lot: lot.product_qty > 0)
        covering = stocked.filtered(lambda lot: lot.product_qty >= self.product_uom_qty)
        if covering:
            return covering[0]
        if stocked:
            return Lot
        return lots[:1]

    @api.onchange('product_id')
    def _onchange_product_id_hc_batch(self):
        if self.lot_id and self.lot_id.product_id == self.product_id:
            return
        self.lot_id = self._hc_default_batch()

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