{
    'name': 'Hospital POS Auto Receipt',
    'version': '1.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'depends': ['sale', 'account', 'stock', 'hospital_management', 'hospital_qz_print'],
    'data': [
        'security/ir.model.access.csv',
        'views/split_payment_action.xml',
        'views/sale_order_view.xml',
        'views/sale_return_wizard_view.xml',
        'views/split_payment_wizard.xml',
        'views/missing_batch_wizard_view.xml',
        'views/pharmacy_checkout_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hospital_pos_auto_receipt/static/src/scss/missing_batch.scss',
            'hospital_pos_auto_receipt/static/src/scss/checkout.scss',
        ],
    },
    'installable': True,
}
