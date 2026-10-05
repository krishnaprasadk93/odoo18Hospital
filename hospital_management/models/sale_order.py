from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    op_ticket_id = fields.Many2one('hospital.op.ticket', string='OP Ticket')
    visit_no = fields.Char(string='Visit No', related='op_ticket_id.visit_no', store=True)
    prescription_ids = fields.One2many(related='op_ticket_id.prescription_ids', string='Prescriptions', readonly=True)
    prescription_note = fields.Html(related='op_ticket_id.prescription_note', string='Prescription Notes',
                                    readonly=True)

    # Override fiscal position to always use Kerala
    fiscal_position_id = fields.Many2one(
        'account.fiscal.position',
        string='Fiscal Position',
        compute='_compute_fiscal_position_kerala',
        store=True,
        readonly=False
    )
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
    @api.depends('partner_id', 'company_id')
    def _compute_fiscal_position_kerala(self):
        '''Always set fiscal position to Kerala (Within Kerala)'''
        for order in self:
            # Try to find Kerala fiscal position
            kerala_fp = self.env['account.fiscal.position'].search([
                ('name', 'ilike', 'kerala')
            ], limit=1)

            if kerala_fp:
                order.fiscal_position_id = kerala_fp
            else:
                # Fallback to default
                order.fiscal_position_id = self.env['account.fiscal.position']._get_fiscal_position(
                    order.partner_id,
                    delivery=order.partner_shipping_id
                )

    def action_confirm(self):
        '''Override to auto-create delivery and invoice'''
        res = super(SaleOrder, self).action_confirm()

        for order in self:
            # Only for pharmacy orders (those linked to OP tickets)
            if order.op_ticket_id:
                # 1. Validate Delivery Order
                for picking in order.picking_ids:
                    if picking.state not in ['done', 'cancel']:
                        # Set quantities done
                        for move in picking.move_ids:
                            move.quantity = move.product_uom_qty
                        # Validate delivery
                        picking.button_validate()

                # 2. Create and Post Invoice
                if not order.invoice_ids:
                    # Create invoice
                    invoice = order._create_invoices()
                    if invoice:
                        # Link to OP ticket
                        invoice.write({'op_ticket_id': order.op_ticket_id.id})
                        # Post invoice
                        invoice.action_post()

        return res
