from odoo import api, fields, models, _
from odoo.exceptions import UserError

EXPIRY_SOON_DAYS = 30


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Display helpers for the medicine list / form (not stored).
    stock_level = fields.Selection([
        ('out', 'Out of stock'),
        ('low', 'Low'),
        ('ok', 'In stock'),
    ], string='Stock Level', compute='_compute_stock_level', search='_search_stock_level')
    nearest_expiry_date = fields.Date(string='Nearest Expiry', compute='_compute_nearest_expiry')
    expiry_state = fields.Selection([
        ('expired', 'Expired'),
        ('soon', 'Expiring soon'),
        ('ok', 'OK'),
    ], string='Expiry', compute='_compute_nearest_expiry', search='_search_expiry_state')
    expiry_text = fields.Char(string='Expiry Status', compute='_compute_nearest_expiry')

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

    # ------------------------------------------------------------------
    # Stock level
    # ------------------------------------------------------------------
    @api.depends('qty_available', 'minimum_qty')
    def _compute_stock_level(self):
        for product in self:
            product.stock_level = product._get_stock_level(product.qty_available)

    def _get_stock_level(self, qty):
        self.ensure_one()
        if qty <= 0:
            return 'out'
        if self.minimum_qty and qty <= self.minimum_qty:
            return 'low'
        return 'ok'

    def _search_stock_level(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            raise UserError(_('Unsupported search on stock level.'))
        values = [value] if isinstance(value, str) else list(value or [])
        medicines = self.search([('is_medicine', '=', True)])
        matched = medicines.filtered(lambda p: p.stock_level in values)
        positive = operator in ('=', 'in')
        return [('id', 'in' if positive else 'not in', matched.ids)]

    # ------------------------------------------------------------------
    # Batch expiry
    # ------------------------------------------------------------------
    def _nearest_expiry_by_product(self, product_ids=None):
        """ {product_id: earliest expiry date} over batches still in stock. """
        domain = [
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
            ('lot_id.expiration_date', '!=', False),
        ]
        if product_ids is not None:
            domain.append(('product_id', 'in', product_ids))
        result = {}
        for quant in self.env['stock.quant'].sudo().search(domain):
            expiry = fields.Date.context_today(self, quant.lot_id.expiration_date)
            current = result.get(quant.product_id.id)
            if not current or expiry < current:
                result[quant.product_id.id] = expiry
        return result

    @api.model
    def _expiry_state_for(self, expiry):
        if not expiry:
            return False
        days = (expiry - fields.Date.context_today(self)).days
        if days < 0:
            return 'expired'
        return 'soon' if days <= EXPIRY_SOON_DAYS else 'ok'

    def _compute_nearest_expiry(self):
        nearest = self._nearest_expiry_by_product(self.ids)
        today = fields.Date.context_today(self)
        for product in self:
            expiry = nearest.get(product.id)
            product.nearest_expiry_date = expiry
            product.expiry_state = self._expiry_state_for(expiry)
            if not expiry:
                product.expiry_text = False
                continue
            days = (expiry - today).days
            if days < 0:
                product.expiry_text = _('Expired %s d ago', -days)
            elif days == 0:
                product.expiry_text = _('Expires today')
            else:
                product.expiry_text = _('Expires in %s d', days)

    def _search_expiry_state(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            raise UserError(_('Unsupported search on expiry.'))
        values = [value] if isinstance(value, str) else list(value or [])
        ids = [pid for pid, expiry in self._nearest_expiry_by_product().items()
               if self._expiry_state_for(expiry) in values]
        positive = operator in ('=', 'in')
        return [('id', 'in' if positive else 'not in', ids)]
