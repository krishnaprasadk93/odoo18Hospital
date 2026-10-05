from odoo import http
from odoo.http import request


class PosPrintController(http.Controller):

    @http.route('/pos/get_printer_settings', type='json', auth='user')
    def get_printer_settings(self):
        settings = request.env['pos.print.settings'].sudo().search([], limit=1)
        return {
            'printer': settings.printer_name,
            'auto_print': settings.auto_print,
            'bold': settings.bold_font,
            'double': settings.double_font,
        }

    @http.route('/pos/check_auto_print', type='json', auth='user')
    def check_auto_print(self):
        inv = request.env['account.move'].sudo().search([
            ('thermal_auto_print', '=', True),
            ('move_type', '=', 'out_invoice')
        ], limit=1)

        if not inv:
            return False

        inv.thermal_auto_print = False

        lines = []
        lines.append("CLINIC RECEIPT\n")
        lines.append("-----------------------------\n")
        lines.append(f"Invoice: {inv.name}\n")
        lines.append(f"Patient: {inv.partner_id.name}\n")
        lines.append("-----------------------------\n")

        for l in inv.invoice_line_ids:
            lines.append(f"{l.name[:15]:15}{l.price_subtotal:>7.2f}\n")

        lines.append("-----------------------------\n")
        lines.append(f"TOTAL: {inv.amount_total:.2f}\n")

        return {
            'print': True,
            'lines': lines
        }
