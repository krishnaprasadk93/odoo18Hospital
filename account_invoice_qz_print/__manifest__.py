# __manifest__.py
{
    "name": "Invoice Direct Print via QZ",
    "version": "18.0.1.0.0",
    "author": "Krishnaprasad K",
    "category": "Healthcare",
    "depends": ["account", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/qz_printer_views.xml",
        "views/account_move_views.xml",
        #"report/invoice_thermal_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_invoice_qz_print/static/src/js/qz_print.js",
        ],
    },
    "license": "LGPL-3",
}
