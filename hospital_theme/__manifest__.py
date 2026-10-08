{
    'name': 'Hospital Theme',
    'version': '18.0.1.1.0',
    'author': 'Krishnaprasad K',
    'category': 'Themes/Backend',
    'summary': 'Clinical teal backend theme: navbar, buttons, forms, lists, company logo '
               'branded login page, Clinic app icon and company name in the tab title',
    'depends': ['web', 'hospital_management'],
    'data': [
        'views/login_templates.xml',
        'data/menu_icon.xml',
    ],
    'assets': {
        # Prepended so these values win over Odoo's `!default` ones, in both
        # the backend and the frontend (login page) bundles.
        'web._assets_primary_variables': [
            ('prepend', 'hospital_theme/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'hospital_theme/static/src/scss/backend.scss',
            'hospital_theme/static/src/js/brand_title.js',
            'hospital_theme/static/src/js/brand_logo.js',
            'hospital_theme/static/src/xml/navbar.xml',
        ],
        'web.assets_frontend': [
            'hospital_theme/static/src/scss/login.scss',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
