from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def hospital_has_custom_logo(self, company_id):
        """ True when the company has its own logo (not Odoo's "Your logo" placeholder). """
        company = self.browse(company_id).exists()
        if not company or not company.logo:
            return False
        return company.logo != self._get_logo()
