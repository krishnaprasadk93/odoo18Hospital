
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

    def action_open_return_wizard(self):
        pass

    def action_view_returns(self):
        pass





