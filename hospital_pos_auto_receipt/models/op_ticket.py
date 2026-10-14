from odoo import models


class HospitalOpTicket(models.Model):
    _inherit = 'hospital.op.ticket'

    def action_create_pharmacy_sale(self):
        return self.env['sale.order']._hc_checkout_action(super().action_create_pharmacy_sale())

    def action_view_sale_orders(self):
        return self.env['sale.order']._hc_checkout_action(super().action_view_sale_orders())
