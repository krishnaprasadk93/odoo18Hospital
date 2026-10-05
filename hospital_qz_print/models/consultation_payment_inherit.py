from odoo import models, fields, api, _


class ConsultationPaymentWizard(models.TransientModel):
    _inherit = 'consultation.payment.wizard'

    def action_process_payment(self):
        # 1. Execute Original Logic (Create Invoice, Payments, Reconcile)
        # This returns the dictionary to open the invoice form (or whatever original logic returned)
        original_result = super(ConsultationPaymentWizard, self).action_process_payment()

        # 2. Extract the Invoice ID from the original return value
        # The original returns: {'res_id': invoice.id, 'res_model': 'account.move', ...}
        invoice_id = original_result.get('res_id') if original_result and isinstance(original_result, dict) else None

        if invoice_id:
            invoice = self.env['account.move'].browse(invoice_id)

            # 3. Generate Print Data (Reuse your existing method on account.move)
            # Ensure _build_escpos_invoice_at301 exists on account.move
            if hasattr(invoice, '_build_escpos_consultaion_invoice_at301'):
                escpos_str = invoice._build_escpos_consultaion_invoice_at301()

                # 4. Return Custom Client Action (Hijack the return)
                return {
                    "type": "ir.actions.client",
                    "tag": "hospital_qz_print",
                    "params": {
                        "escpos_raw": escpos_str,
                        "notification": {
                            "type": "success",
                            "title": _("Payment Successful"),
                            "message": _("Invoice created. Printing receipt..."),
                            "sticky": False,
                        }
                    },
                }

        # Fallback: If no invoice found or method missing, return the original action
        return original_result
