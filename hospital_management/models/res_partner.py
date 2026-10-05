from odoo import models, api
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []

        if name:
            domain = expression.OR([
                [('name', operator, name)],
                [('phone', operator, name)],
                [('mobile', operator, name)],
            ])

            partners = self.search(
                expression.AND([domain, args]),
                limit=limit
            )
        else:
            partners = self.search(args, limit=limit)

        return [(p.id, p.display_name) for p in partners]

    @api.depends('name', 'phone', 'mobile')
    def _compute_display_name(self):
        for partner in self:
            name = partner.name or ''
            phone = partner.phone or partner.mobile or ''

            if phone:
                partner.display_name = f"{name} - {phone}"
            else:
                partner.display_name = name