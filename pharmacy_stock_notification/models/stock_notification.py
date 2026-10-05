from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PharmacyStockNotification(models.Model):
    _name = 'pharmacy.stock.notification'
    _description = 'Pharmacy Stock Notification'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New')
    )

    product_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        readonly=True,
        states={'pending': [('readonly', False)]},
        tracking=True
    )

    product_code = fields.Char(
        related='product_id.default_code',
        string='Product Code',
        store=True,
        readonly=True
    )

    current_qty = fields.Float(
        string='Current Stock',
        digits='Product Unit of Measure',
        readonly=True
    )

    minimum_qty = fields.Float(
        string='Minimum Required',
        digits='Product Unit of Measure',
        readonly=True
    )

    shortage_qty = fields.Float(
        string='Shortage Quantity',
        digits='Product Unit of Measure',
        readonly=True,
        help='Difference between minimum and current stock'
    )

    uom_id = fields.Many2one(
        related='product_id.uom_id',
        string='Unit of Measure',
        readonly=True
    )

    state = fields.Selection([
        ('pending', 'Pending'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    ], string='Status', default='pending', tracking=True, required=True)

    acknowledged_by = fields.Many2one(
        'res.users',
        string='Acknowledged By',
        readonly=True,
        tracking=True
    )

    acknowledged_date = fields.Datetime(
        string='Acknowledged Date',
        readonly=True
    )

    notes = fields.Text(string='Notes')

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pharmacy.stock.notification'
                ) or _('New')

        records = super().create(vals_list)

        # Send notification to pharmacy group users
        for record in records:
            record._notify_pharmacy_users()

        return records

    def _notify_pharmacy_users(self):
        """Send notification to pharmacy group users"""
        self.ensure_one()

        # Get pharmacy group users
        pharmacy_group = self.env.ref(
            'pharmacy_stock_notification.group_pharmacy_user',
            raise_if_not_found=False
        )

        if not pharmacy_group:
            return

        users = pharmacy_group.users

        if not users:
            return

        # Create activity for each user
        for user in users:
            self.activity_schedule(
                'pharmacy_stock_notification.mail_activity_low_stock',
                user_id=user.id,
                summary=f'Low Stock Alert: {self.product_id.name}',
                note=f'''Product: {self.product_id.name}<br/>
                Current Stock: {self.current_qty} {self.uom_id.name}<br/>
                Minimum Required: {self.minimum_qty} {self.uom_id.name}<br/>
                Shortage: {self.shortage_qty} {self.uom_id.name}'''
            )
            # 2. NEW: Send Real-time Pop-up Notification (Toast)
            # This sends a notification to the user's interface immediately
            self.env['bus.bus']._sendone(user.partner_id, 'simple_notification', {
                'type': 'danger',  # 'danger' makes it red, 'warning' yellow
                'title': _('Low Stock Alert!'),
                'message': f"{self.product_id.name} is below minimum stock! ({self.current_qty} remaining)",
                'sticky': True,  # True = User must close it manually; False = Disappears auto
            })
        # Post message
        self.message_post(
            body=f'''Low Stock Alert Created!<br/>
            <b>Product:</b> {self.product_id.name}<br/>
            <b>Current Stock:</b> {self.current_qty} {self.uom_id.name}<br/>
            <b>Minimum Required:</b> {self.minimum_qty} {self.uom_id.name}<br/>
            <b>Action Required:</b> Please restock this item.''',
            subject='Low Stock Alert',
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
        )

    def action_acknowledge(self):
        """Acknowledge the notification"""
        self.ensure_one()

        if self.state != 'pending':
            raise UserError(_('Only pending notifications can be acknowledged.'))

        self.write({
            'state': 'acknowledged',
            'acknowledged_by': self.env.user.id,
            'acknowledged_date': fields.Datetime.now(),
        })

        # Mark activities as done
        self.activity_ids.action_feedback(feedback='Notification acknowledged')

        # Post message
        self.message_post(
            body=f'Notification acknowledged by {self.env.user.name}',
            subject='Notification Acknowledged',
        )

        return True

    def action_resolve(self):
        """Mark notification as resolved"""
        self.ensure_one()

        self.write({
            'state': 'resolved',
        })

        # Mark activities as done
        self.activity_ids.action_feedback(feedback='Issue resolved')

        # Post message
        self.message_post(
            body=f'Notification resolved by {self.env.user.name}',
            subject='Notification Resolved',
        )

        return True

    def action_check_current_stock(self):
        """Refresh current stock quantity"""
        self.ensure_one()

        current_qty = self.product_id.qty_available

        self.write({
            'current_qty': current_qty,
            'shortage_qty': self.minimum_qty - current_qty,
        })

        # If stock is now sufficient, auto-resolve
        if current_qty >= self.minimum_qty:
            self.action_resolve()

        return True
