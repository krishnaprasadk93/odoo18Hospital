# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    list_price = fields.Float(help="")

    minimum_qty = fields.Float(
        string='Minimum Stock Quantity',
        default=0.0,
        help='',
        digits='Product Unit of Measure'
    )

    enable_low_stock_alert = fields.Boolean(
        string='Enable Low Stock Alert',
        default=True,
        help=''
    )

    low_stock_notification_ids = fields.One2many(
        'pharmacy.stock.notification',
        'product_id',
        string='Stock Notifications'
    )

    low_stock_notification_count = fields.Integer(
        string='Notification Count',
        compute='_compute_notification_count'
    )

    @api.depends('low_stock_notification_ids')
    def _compute_notification_count(self):
        for record in self:
            record.low_stock_notification_count = len(
                record.low_stock_notification_ids.filtered(lambda n: n.state == 'pending')
            )

    def action_view_notifications(self):
        """Open notifications for this product"""
        self.ensure_one()
        return {
            'name': f'Low Stock Notifications - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.stock.notification',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id}
        }

    def check_stock_level(self):
        """Check if current stock is below minimum and create notification"""
        self.ensure_one()

        if not self.enable_low_stock_alert or self.minimum_qty <= 0:
            return

        # Get current stock quantity
        current_qty = self.qty_available

        # Check if below minimum
        if current_qty < self.minimum_qty:
            # Check if notification already exists for pending state
            existing_notification = self.env['pharmacy.stock.notification'].search([
                ('product_id', '=', self.id),
                ('state', '=', 'pending')
            ], limit=1)

            if not existing_notification:
                # Create new notification
                self.env['pharmacy.stock.notification'].create({
                    'product_id': self.id,
                    'current_qty': current_qty,
                    'minimum_qty': self.minimum_qty,
                    'shortage_qty': self.minimum_qty - current_qty,
                })

    @api.model
    def cron_check_all_stock_levels(self):
        """
        Scheduled action to check all products with low stock alerts enabled.
        Runs daily at 8:00 AM to check stock levels.
        """
        # Get all products with low stock alert enabled
        products = self.search([
            ('enable_low_stock_alert', '=', True),
            ('minimum_qty', '>', 0)
        ])

        checked_count = 0
        notification_count = 0

        for product in products:
            checked_count += 1

            current_qty = product.qty_available

            # Check if below minimum
            if current_qty < product.minimum_qty:
                # Check if notification already exists for pending state
                existing_notification = self.env['pharmacy.stock.notification'].search([
                    ('product_id', '=', product.id),
                    ('state', '=', 'pending')
                ], limit=1)

                if not existing_notification:
                    # Create new notification
                    self.env['pharmacy.stock.notification'].create({
                        'product_id': product.id,
                        'current_qty': current_qty,
                        'minimum_qty': product.minimum_qty,
                        'shortage_qty': product.minimum_qty - current_qty,
                    })
                    notification_count += 1

        # Log the cron execution
        _logger = self.env['ir.logging']
        _logger.sudo().create({
            'name': 'Pharmacy Stock Check',
            'type': 'server',
            'dbname': self.env.cr.dbname,
            'level': 'INFO',
            'message': f'Daily stock check completed. Checked {checked_count} products. Created {notification_count} new notifications.',
            'path': 'pharmacy_stock_notification',
            'func': 'cron_check_all_stock_levels',
            'line': '1'
        })

        return True
