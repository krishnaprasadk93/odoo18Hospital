from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super().action_post()

        for pay in self:
            # Find related invoice
            invoices = pay.reconciled_invoice_ids
            for inv in invoices:
                # Only when fully paid
                if inv.payment_state == 'paid':
                    # inv.sudo().write({'thermal_auto_print': True})
                    inv._send_to_thermal_printer()

        return res
