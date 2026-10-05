
from odoo import models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_open_custom_return_wizard(self):
        self.ensure_one()
        lines = []
        for line in self.order_line.filtered(lambda l: l.product_uom_qty > 0):
            lines.append((0, 0, {
                'so_line_id': line.id,
                'product_id': line.product_id.id,
                'ordered_qty': line.product_uom_qty,
                'return_qty': 0.0,
            }))

        if not lines:
            raise UserError("No order lines available to return.")

        return {
            'name': 'Process Return',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_line_ids': lines,
            }
        }

    def action_reprint_qz_receipt(self):
        self.ensure_one()

        # 1. Find the relevant invoice
        # Prefer 'posted' invoices, otherwise take any (e.g. draft)
        invoices = self.invoice_ids.filtered(lambda x: x.state == 'posted')
        if not invoices:
            invoices = self.invoice_ids

        if not invoices:
            raise UserError("No invoice found linked to this Sale Order.")

        # 2. Pick the most recent one
        target_invoice = invoices[-1]

        # 3. Generate Print Data (Reuse logic from account.move)
        if hasattr(target_invoice, '_build_escpos_invoice_at301'):
            escpos_str = target_invoice._build_escpos_invoice_at301()

            # 4. Return Client Action
            return {
                "type": "ir.actions.client",
                "tag": "hospital_qz_print",
                "params": {
                    "escpos_raw": escpos_str,
                    "notification": {
                        "type": "success",
                        "title": "Reprinting",
                        "message": "Receipt sent to printer.",
                        "sticky": False,
                    }
                },
            }
        else:
            raise UserError("Print function (_build_escpos_invoice_at301) not found on Invoice model.")

    def _get_products_missing_batch(self):
        """ Lot-tracked stockable products on this order that have no batch
        (stock.lot) at all, so their delivery cannot be auto-validated. """
        self.ensure_one()
        products = self.order_line.product_id.filtered(
            lambda p: p.is_storable and p.tracking != 'none')
        if not products:
            return products
        lots = self.env['stock.lot'].search([
            ('product_id', 'in', products.ids),
            ('company_id', 'in', (False, self.company_id.id)),
        ])
        return products - lots.product_id

    def _action_split_payment_wizard(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'hospital_pos_auto_receipt.action_split_payment_wizard')
        action['context'] = {
            'active_id': self.id,
            'active_ids': self.ids,
            'active_model': 'sale.order',
            'default_sale_id': self.id,
        }
        return action

    def _action_missing_batch_wizard(self, missing, next_step):
        return {
            'name': 'No Batch Found',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.missing.batch.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_id': self.id,
                'default_next_step': next_step,
                'default_line_ids': [(0, 0, {'product_id': p.id}) for p in missing],
            },
        }

    def action_open_split_payment(self):
        """ "Confirm and Pay": ask for a batch number first for any medicine
        that has no batch yet, then open the split payment wizard. """
        self.ensure_one()
        missing = self._get_products_missing_batch()
        if missing:
            return self._action_missing_batch_wizard(missing, 'pay')
        return self._action_split_payment_wizard()

    def action_confirm_check_batch(self):
        """ "Confirm": same batch check as "Confirm and Pay", then confirm. """
        self.ensure_one()
        missing = self._get_products_missing_batch()
        if missing:
            return self._action_missing_batch_wizard(missing, 'confirm')
        return self.action_confirm()

    def action_open_return_wizard(self):
        pass

    def action_view_returns(self):
        pass





