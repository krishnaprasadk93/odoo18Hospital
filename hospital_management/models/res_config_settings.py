from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    revisit_limit_days = fields.Integer(
        string="Revisit Limit Days",
        config_parameter='hospital.revisit_limit_days',
        default=15,
        help="If patient revisits within these days, consultation is free."
    )
    revisit_check_type = fields.Selection(
        [
            ('hospital', 'Hospital Wise'),
            ('doctor', 'Doctor Wise'),
        ],
        string="Revisit Check Based On",
        config_parameter='hospital.revisit_check_type',
        default='hospital',
    )
    hospital_cash_journal_id = fields.Many2one(
        related='company_id.hospital_cash_journal_id', readonly=False)
    hospital_card_journal_id = fields.Many2one(
        related='company_id.hospital_card_journal_id', readonly=False)
    hospital_upi_journal_id = fields.Many2one(
        related='company_id.hospital_upi_journal_id', readonly=False)
    require_amount_collected_entry = fields.Boolean(
        string="Require Amount Collected for Cash Payments",
        config_parameter='hospital.require_amount_collected_entry',
        help="If enabled, whenever a payment includes a Cash amount greater "
             "than zero, the cashier must enter the Amount Given by Customer "
             "before the invoice/payment can be processed."
    )
