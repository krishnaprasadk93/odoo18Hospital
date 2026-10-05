{
    'name': 'Sale Stock - Allow Negative Stock',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Deliveries of confirmed sale orders are always Ready, '
               'even without stock (allows negative stock)',
    'description': """
When a sale order is confirmed and there is not enough stock, Odoo leaves the
delivery order in the "Waiting" state and it cannot be validated without
manual quantity encoding.

With this module (enabled per company in Inventory > Settings > Operations >
"Allow Negative Stock on Sales"), the missing quantity is force-reserved on
the delivery so it becomes "Ready" and can be validated directly. On
validation the on-hand quantity goes negative.

Products tracked by lot/serial number are not forced (a lot is required).
""",
    'depends': ['sale_stock'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
}
