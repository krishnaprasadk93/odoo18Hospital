{
    'name': 'Hospital Sales Dashboard',
    'version': '18.0.1.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Sales dashboard for doctors: pharmacy (OP) and OTC sales, '
               'payments by method, top products and customers, receivables',
    'depends': ['hospital_doctor_dashboard', 'hospital_management', 'sale_management', 'account'],
    'data': [
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_sales_dashboard/static/src/dashboard/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
