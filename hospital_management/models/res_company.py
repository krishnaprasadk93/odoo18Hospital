from odoo import _, fields, models
from odoo.addons.hospital_management.exceptions import ClinicError


class ResCompany(models.Model):
    _inherit = 'res.company'

    hospital_cash_journal_id = fields.Many2one(
        'account.journal', string='Cash Payment Journal', check_company=True,
        domain="[('type', '=', 'cash'), ('company_id', '=', id)]")
    hospital_card_journal_id = fields.Many2one(
        'account.journal', string='Card Payment Journal', check_company=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]")
    hospital_upi_journal_id = fields.Many2one(
        'account.journal', string='UPI Payment Journal', check_company=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]")

    def _check_hospital_payment_journals(self, splits):
        """ `splits` is a list of (label, amount, journal). Every method with
        an amount must have a journal, otherwise its payment would be
        silently skipped and the invoice left part-unpaid. """
        missing = [label for label, amount, journal in splits if amount > 0 and not journal]
        if missing:
            raise ClinicError(_("Payment journal missing"), _(
                "No journal is selected for: %(methods)s.\n\n"
                "Pick one on the payment tile, or set default journals in "
                "Settings > Clinic > Payments.",
                methods=", ".join(missing)))
