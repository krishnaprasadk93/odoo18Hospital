{
    'name': 'Hospital Doctor Dashboard',
    'version': '18.0.1.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Clinic dashboard for doctors: visits, patients, prescriptions '
               'and revenue across hospitals, by date range',
    'depends': ['hospital_management', 'web'],
    'data': [
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_doctor_dashboard/static/src/dashboard/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
