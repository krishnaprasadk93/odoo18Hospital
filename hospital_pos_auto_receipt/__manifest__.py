{
    'name': 'Hospital POS Auto Receipt',
    'version': '1.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'depends': ['sale', 'account', 'stock', 'hospital_qz_print'],
    'data': [
        'security/ir.model.access.csv',
        'views/split_payment_action.xml',
        'views/sale_order_view.xml',
        'views/sale_return_wizard_view.xml',
        'views/split_payment_wizard.xml',
    ],
    'installable': True,
}
