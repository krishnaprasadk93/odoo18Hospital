{
    'name': 'Hospital Inventory Dashboard',
    'version': '18.0.1.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Full-screen pharmacy inventory dashboard: stock value, batches, '
               'expiry, negative and low stock, medicines without batch',
    'depends': ['hospital_doctor_dashboard', 'hospital_management', 'pharmacy_stock_notification', 'stock'],
    'data': [
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_inventory_dashboard/static/src/dashboard/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
