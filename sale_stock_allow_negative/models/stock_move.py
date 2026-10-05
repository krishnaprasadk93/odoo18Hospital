from odoo import models
from odoo.tools import float_compare


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _should_force_negative_availability(self):
        """ Moves of a sale order taking goods out of stock, which could not
        be fully reserved, and are not waiting on a previous step. """
        self.ensure_one()
        return (
            self.sale_line_id
            and self.company_id.sale_allow_negative_stock
            and self.state in ('confirmed', 'partially_available')
            and not self.picked
            and not self.move_orig_ids
            and self.procure_method == 'make_to_stock'
            and self.product_id.is_storable
            and self.product_id.tracking == 'none'
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
        return res
