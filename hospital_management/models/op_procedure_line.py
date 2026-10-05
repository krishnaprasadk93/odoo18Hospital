from odoo import models, fields, api


class OpProcedureLine(models.Model):
    _name = 'op.procedure.line'
    _description = 'OP Procedure Line'
    _rec_name = 'product_id'

    op_ticket_id = fields.Many2one('hospital.op.ticket', string='OP Ticket', ondelete='cascade')

    product_id = fields.Many2one(
        'product.product',
        string="Procedure",
        domain=[('type', '=', 'service'), ('is_procedure', '=', True)],
        required=True
    )
    qty = fields.Float(string="Qty", default=1)
    price_unit = fields.Float(string="Price")
    description = fields.Html(string="Procedure Description")
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True
    )

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.qty * rec.price_unit

    @api.onchange('product_id')
    def _onchange_product(self):
        for rec in self:
            if rec.product_id:
                rec.price_unit = rec.product_id.lst_price

                # Load default description template
                rec.description = rec.product_id.description or False
