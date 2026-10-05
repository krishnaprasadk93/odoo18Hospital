from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    op_ticket_id = fields.Many2one('hospital.op.ticket', string='OP Ticket')
    doctor_id = fields.Many2one(
        'hr.employee',
        related='op_ticket_id.doctor_id',
        store=True
    )

    amount_collected = fields.Float(
        string='Amount Collected',
        help='Total cash physically handed over by the customer.'
    )
    balance_amount = fields.Float(
        string='Balance Returned',
        help='Change returned to the customer (Amount Collected - Cash Amount).'
    )
    is_cash_payment = fields.Boolean(
        string='Paid Fully in Cash',
        help='True when this invoice was settled entirely via a cash journal '
             '(no card/UPI split), so the receipt can print the collected '
             'amount and balance returned.'
    )
