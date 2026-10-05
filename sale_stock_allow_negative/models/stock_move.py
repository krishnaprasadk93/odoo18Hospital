from odoo import fields, models
from odoo.tools import float_compare


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_forced_lot(self):
        """ Lot to use when forcing availability of a tracked product: the
        batch chosen on the sale order line (field added by other modules,
        e.g. hospital_management), otherwise the product's existing lot that
        expires first (FEFO), preferring lots not yet expired. """
        self.ensure_one()
        sale_line = self.sale_line_id
        if 'lot_id' in sale_line._fields and sale_line.lot_id:
            return sale_line.lot_id
        Lot = self.env['stock.lot']
        domain = [
            ('product_id', '=', self.product_id.id),
            ('company_id', 'in', (False, self.company_id.id)),
        ]
        if 'expiration_date' not in Lot._fields:
            return Lot.search(domain, order='create_date desc, id desc', limit=1)
        valid = Lot.search(
            domain + ['|', ('expiration_date', '=', False),
                      ('expiration_date', '>=', fields.Datetime.now())],
            order='expiration_date asc, id asc', limit=1)
        return valid or Lot.search(domain, order='expiration_date desc, id desc', limit=1)

    def _should_force_negative_availability(self):
        """ Moves of a sale order taking goods out of stock, which could not
        be fully reserved, and are not waiting on a previous step.
        Tracked products are only forced when a lot is known (see
        `_get_forced_lot`), since a move line needs one to be validated. """
        self.ensure_one()
        return (
            self.sale_line_id
            and self.company_id.sale_allow_negative_stock
            and self.state in ('confirmed', 'partially_available')
            and not self.picked
            and not self.move_orig_ids
            and self.procure_method == 'make_to_stock'
            and self.product_id.is_storable
            and (self.product_id.tracking == 'none' or self._get_forced_lot())
            and self.location_id.usage == 'internal'
            and not self._should_bypass_reservation()
            and float_compare(self.quantity, self.product_uom_qty,
                              precision_rounding=self.product_uom.rounding) < 0
        )

    def _action_assign(self, force_qty=False):
        # Only forward force_qty when set: some custom overrides of
        # `_action_assign` don't accept the argument.
        if force_qty:
            res = super()._action_assign(force_qty=force_qty)
        else:
            res = super()._action_assign()
        if not force_qty and not self.env.context.get('skip_force_negative_availability'):
            for move in self.filtered(lambda m: m._should_force_negative_availability()):
                # Setting the quantity creates the missing move lines from the
                # move's source location (see `_set_quantity_done_prepare_vals`),
                # the move becomes 'assigned' and the quant goes negative on validation.
                move.quantity = move.product_uom_qty
                lot = move._get_forced_lot()
                if lot:
                    move.move_line_ids.filtered(lambda ml: not ml.lot_id).lot_id = lot
        return res
