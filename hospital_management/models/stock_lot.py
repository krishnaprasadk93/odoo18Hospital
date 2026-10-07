from odoo import models, fields, api
from odoo.exceptions import ValidationError


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # ====================================
    # Pharmacy Fields
    # ====================================

    selling_price = fields.Float(string="Selling Price")

    margin_percent = fields.Float(
        string="Margin %",
        compute="_compute_margin",
        store=True
    )

    available_qty = fields.Float(
        string="Available Quantity",
        compute="_compute_available_qty"
    )
    expiry_state = fields.Selection([
        ('expired', 'Expired'),
        ('soon', 'Expiring soon'),
        ('ok', 'OK'),
    ], string="Expiry Status", compute="_compute_expiry_state")
    expiry_date_only = fields.Date(string="Expiry", compute="_compute_expiry_state")

    @api.depends('expiration_date')
    def _compute_expiry_state(self):
        Product = self.env['product.product']
        for lot in self:
            expiry = fields.Date.context_today(lot, lot.expiration_date) if lot.expiration_date else False
            lot.expiry_date_only = expiry
            lot.expiry_state = Product._expiry_state_for(expiry)

    # ====================================
    # Margin Calculation
    # ====================================

    @api.depends('selling_price', 'standard_price')
    def _compute_margin(self):
        for lot in self:
            cost = lot.standard_price
            if cost:
                lot.margin_percent = ((lot.selling_price - cost) / cost) * 100
            else:
                lot.margin_percent = 0.0

    # ====================================
    # Batch-wise Stock Quantity
    # ====================================

    def _compute_available_qty(self):
        for lot in self:
            quants = self.env['stock.quant'].search([
                ('lot_id', '=', lot.id),
                ('location_id.usage', '=', 'internal')
            ])
            lot.available_qty = sum(quants.mapped('quantity'))

    # ====================================
    # Prevent Duplicate Batch Per Product
    # ====================================

    _sql_constraints = [
        (
            'unique_batch_per_product',
            'unique(name, product_id)',
            'Batch number must be unique per product!'
        )
    ]
