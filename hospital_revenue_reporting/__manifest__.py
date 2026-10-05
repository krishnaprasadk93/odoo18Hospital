
{
    'name': 'Hospital Revenue Reporting',
    'version': '18.0.2.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Advanced Hospital Revenue Excel Reports',
    'depends': ['account', 'sale', 'hr', 'board', 'hospital_management'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/revenue_wizard_view.xml',
        'reports/revenue_report.xml',
        'views/dashboard_views.xml',
        'menus/menus.xml',
    ],
    'installable': True,
    'application': False,
}
