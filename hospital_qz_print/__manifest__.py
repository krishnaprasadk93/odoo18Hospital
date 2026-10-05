{
    'name': 'Hospital QZ Direct Print',
    'version': '18.0.1.0.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Automated QZ Tray Printing after Consultation Payment',
    'description': """
        This module extends the Consultation Payment Wizard to automatically print
        receipts via QZ Tray upon successful payment processing.
        It intercepts the original wizard action and returns a client action
        that triggers the print job without redirecting the user.
    """,
    'depends': ['web', 'account', 'hospital_management'], 
    'data': [
        'views/ticket_action.xml',  # <-- Add this line
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_qz_print/static/src/js/qz_print_action.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}