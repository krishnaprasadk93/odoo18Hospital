from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        res = super().action_post()
        return self.env.ref('hospital_invoice_80mm.action_report_invoice_80mm').report_action(self)

    def _send_to_thermal_printer(self):
        settings = self.env['pos.print.settings'].sudo().search([], limit=1)

        if not settings or not settings.auto_print:
            return

        return {
            'type': 'ir.actions.client',
            'tag': 'thermal_print_receipt',
            'params': {
                'invoice_id': self.id,
            }
        }

    def action_send_to_thermal_printer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'thermal_print_invoice',
            'params': {'invoice_id': self.id}
        }

    def action_print_thermal(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'thermal_print_invoice',
            'params': {'invoice_id': self.id}
        }

