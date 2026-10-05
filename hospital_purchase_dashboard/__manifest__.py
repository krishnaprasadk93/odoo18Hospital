{
    'name': 'Hospital Purchase Dashboard',
    'version': '18.0.1.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Purchase dashboard for doctors: spend, vendors, products, '
               'pending receipts and vendor bills ageing',
    'depends': ['hospital_doctor_dashboard', 'hospital_management', 'purchase_stock', 'account'],
    'data': [
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_purchase_dashboard/static/src/dashboard/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
