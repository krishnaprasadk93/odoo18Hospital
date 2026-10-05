from odoo import models, fields
from odoo.exceptions import UserError


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

    def _action_assign(self):
        res = super()._action_assign()
        today = fields.Date.today()

        for move in self:
            if move.picking_id.picking_type_id.code != 'outgoing':
                continue
            if not move.product_id.product_tmpl_id.is_medicine:
                continue

            # ✅ MANUAL LOT: Force-set lot_id on all move lines created by super()
            if move.sale_line_id and move.sale_line_id.lot_id:
                move.move_line_ids.write({'lot_id': move.sale_line_id.lot_id.id})
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
