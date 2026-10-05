from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        vals = super()._prepare_move_line_vals(quantity, reserved_quant)

        # If batch selected in sale order line
        if self.sale_line_id and self.sale_line_id.lot_id:
            vals['lot_id'] = self.sale_line_id.lot_id.id

        return vals

    def _action_assign_old(self):
        res = super()._action_assign()

        today = fields.Date.today()

        for move in self:

            # 🔴 VERY IMPORTANT:
            # Apply only for OUTGOING (Customer Delivery)
            if move.picking_id.picking_type_id.code != 'outgoing':
                continue

            # Only medicines
            if not move.product_id.product_tmpl_id.is_medicine:
                continue

            # If batch manually selected → skip
            if move.sale_line_id and move.sale_line_id.lot_id:
                continue

            required_qty = move.product_uom_qty
            assigned_qty = 0

            quant_data = self.env['stock.quant'].read_group(
                domain=[
                    ('product_id', '=', move.product_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0),
                    ('lot_id.expiration_date', '>=', today),
                ],
                fields=['quantity:sum', 'lot_id'],
                groupby=['lot_id'],
            )

            if not quant_data:
                continue

            lot_data = []
            for data in quant_data:
                if not data['lot_id']:
                    continue

                lot = self.env['stock.lot'].browse(data['lot_id'][0])
                lot_data.append({
                    'lot': lot,
                    'qty': data['quantity'],
                    'expiry': lot.expiration_date or fields.Datetime.max
                })

            lot_data = sorted(lot_data, key=lambda x: x['expiry'])

            move.move_line_ids.unlink()

            for item in lot_data:
                lot = item['lot']
                lot_qty = item['qty']

                take_qty = min(required_qty - assigned_qty, lot_qty)

                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'lot_id': lot.id,
                    'quantity': take_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                })

                assigned_qty += take_qty

                if assigned_qty >= required_qty:
                    break

        return res

    def _action_assign(self, force_qty=False):
        res = super()._action_assign(force_qty=force_qty)
        today = fields.Date.today()

        for move in self:
            if move.picking_id.picking_type_id.code != 'outgoing':
                continue
            if not move.product_id.product_tmpl_id.is_medicine:
                continue

            # ✅ MANUAL LOT: Force-set lot_id on all move lines created by super()
            if move.sale_line_id and move.sale_line_id.lot_id:
                move.move_line_ids.write({'lot_id': move.sale_line_id.lot_id.id})
                move._force_medicine_shortfall(move.sale_line_id.lot_id)
                continue  # Skip FEFO auto-assignment

            # AUTO FEFO assignment for medicines without manual lot
            required_qty = move.product_uom_qty
            assigned_qty = 0

            quant_data = self.env['stock.quant'].read_group(
                domain=[
                    ('product_id', '=', move.product_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0),
                    ('lot_id.expiration_date', '>=', today),
                ],
                fields=['quantity:sum', 'lot_id'],
                groupby=['lot_id'],
            )
            if not quant_data:
                # No batch in stock: sell from a batch anyway (negative stock)
                move._force_medicine_shortfall(move._get_medicine_fallback_lot())
                continue

            lot_data = []
            for data in quant_data:
                if not data['lot_id']:
                    continue
                lot = self.env['stock.lot'].browse(data['lot_id'][0])
                lot_data.append({
                    'lot': lot,
                    'qty': data['quantity'],
                    'expiry': lot.expiration_date or fields.Datetime.max
                })
            lot_data = sorted(lot_data, key=lambda x: x['expiry'])

            move.move_line_ids.unlink()
            for item in lot_data:
                lot = item['lot']
                lot_qty = item['qty']
                take_qty = min(required_qty - assigned_qty, lot_qty)
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'lot_id': lot.id,
                    'quantity': take_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                })
                assigned_qty += take_qty
                if assigned_qty >= required_qty:
                    break

            # Batches don't cover the demand: put the rest on the latest-expiry batch
            fallback_lot = lot_data[-1]['lot'] if lot_data else move._get_medicine_fallback_lot()
            move._force_medicine_shortfall(fallback_lot)
        return res

    def _get_medicine_fallback_lot(self):
        """ Batch to sell from when no batch has stock: the latest unexpired one,
        else the most recent one. """
        self.ensure_one()
        Lot = self.env['stock.lot']
        domain = [
            ('product_id', '=', self.product_id.id),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ]
        return (
            Lot.search(domain + [('expiration_date', '>=', fields.Date.today())],
                       order='expiration_date desc', limit=1)
            or Lot.search(domain, order='id desc', limit=1)
        )

    def _force_medicine_shortfall(self, lot):
        """ Reserve the quantity no batch could cover on `lot`, so the delivery is
        Ready instead of Waiting and the batch goes negative on validation. """
        self.ensure_one()
        company = self.company_id
        if 'sale_allow_negative_stock' in company._fields and not company.sale_allow_negative_stock:
            return
        if not lot or self.product_id.tracking == 'none' or self.state in ('done', 'cancel'):
            return
        missing = self.product_uom_qty - self.quantity
        if float_compare(missing, 0, precision_rounding=self.product_uom.rounding) <= 0:
            return
        self.env['stock.move.line'].create({
            'move_id': self.id,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'lot_id': lot.id,
            'quantity': missing,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
        })
        self._recompute_state()
