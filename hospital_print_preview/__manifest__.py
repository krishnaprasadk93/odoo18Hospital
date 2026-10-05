{
    'name': 'Hospital Print Preview',
    'version': '18.0.1.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Optional print preview before sending thermal receipts to QZ Tray',
    'description': """
        Adds a "Show Print Preview" setting. When enabled, invoice / consultation /
        pharmacy receipts that would normally print directly via QZ Tray instead
        open a preview of the 80mm thermal receipt with a Print button, so the
        user can review before printing. When disabled, printing works exactly
        as before (direct print, no preview).
    """,
    'depends': ['web', 'hospital_management', 'hospital_qz_print', 'account_invoice_qz_print'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_print_preview/static/src/js/escpos_parser.js',
            'hospital_print_preview/static/src/js/print_preview_dialog.js',
            'hospital_print_preview/static/src/js/qz_print_preview_action.js',
            'hospital_print_preview/static/src/xml/print_preview_dialog.xml',
            'hospital_print_preview/static/src/css/print_preview.css',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
