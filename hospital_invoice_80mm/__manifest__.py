
{
    'name': 'Hospital Invoice 80mm',
    'version': '18.0.2.0.0',
    'depends': ['base','account','hospital_management','web'],
    'category': 'Healthcare',
    'data': [
        'security/ir.model.access.csv',
        'report/report_invoice_80mm.xml',
        'report/invoice_80mm_template.xml',
        'views/invoice_button.xml',
        'views/pos_print_settings_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_invoice_80mm/static/src/js/thermal_print.js',
        ],
    },

    'installable': True,
}