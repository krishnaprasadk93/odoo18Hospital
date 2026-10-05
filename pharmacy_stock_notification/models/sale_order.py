# -*- coding: utf-8 -*-
from odoo import models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Override to check stock levels after sale confirmation"""
        res = super().action_confirm()

        # Check stock levels for all products in the order
        for line in self.order_line:
            if line.product_id.product_tmpl_id:
                line.product_id.product_tmpl_id.check_stock_level()

        return res
