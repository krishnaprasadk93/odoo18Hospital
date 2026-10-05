{
    'name': 'Hospital POS Receipt',
    'version': '1.0',
    'author': 'Krishnaprasad K',
    'category': 'Healthcare',
    'summary': 'Print Consultation Receipts in POS format',
    'depends': ['hospital_management', 'account'],
    'data': [
        'reports/paper_format.xml',
        'reports/consultation_receipt_report.xml',
    ],
    'installable': True,
    'application': False,
}
