{
    'name': 'Pharmacy Stock Notification',
    'version': '18.0.1.0.0',
    'category': 'Healthcare',
    'summary': 'Low Stock Alerts & Notifications for Pharmacy',
    'description': '''
        Pharmacy Stock Notification System
        ===================================

        Features:
        ---------
        * Add minimum quantity field to products
        * Automatic low stock detection when sales occur
        * Send notifications to Pharmacy group users
        * Notification shows product details and current stock
        * Pharmacy users can acknowledge/accept notifications
        * Activity tracking for low stock items

        Perfect for pharmacy and hospital inventory management.
    ''',
    'author': 'Krishnaprasad K',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'product',
        'stock',
        'sale',
        'mail',
    ],
    'data': [
        'security/pharmacy_security.xml',
        'security/ir.model.access.csv',
        'data/mail_activity_type_data.xml',
        'data/ir_cron_data.xml',
        'views/product_template_views.xml',
        'views/stock_notification_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
