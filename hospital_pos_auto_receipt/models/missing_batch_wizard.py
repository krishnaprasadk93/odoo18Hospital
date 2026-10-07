from odoo import fields, models
from odoo.exceptions import UserError


class SaleMissingBatchWizard(models.TransientModel):
    _name = 'sale.missing.batch.wizard'
    _description = 'Create Missing Batches Before Payment'

    sale_id = fields.Many2one('sale.order', required=True, readonly=True)
    next_step = fields.Selection(
        [('pay', 'Continue to Payment'), ('confirm', 'Confirm Order')],
        default='pay', required=True)
    line_ids = fields.One2many('sale.missing.batch.wizard.line', 'wizard_id', string='Medicines')

    def action_create_batches(self):
        """ Create the entered batches, use them on the order lines, then
        continue: to the split payment wizard, or confirm the order. """
        self.ensure_one()
        missing_name = self.line_ids.filtered(lambda l: not (l.lot_name or '').strip())
        if missing_name:
            raise UserError(
                "Enter a Batch No for: %s" % ", ".join(missing_name.product_id.mapped('display_name')))

        Lot = self.env['stock.lot']
        for line in self.line_ids:
            vals = {
                'name': line.lot_name.strip(),
                'product_id': line.product_id.id,
                'company_id': self.sale_id.company_id.id,
            }
            if line.expiration_date and 'expiration_date' in Lot._fields:
                vals['expiration_date'] = line.expiration_date
            lot = Lot.create(vals)
            self.sale_id.order_line.filtered(
                lambda l: l.product_id == line.product_id and not l.lot_id
            ).lot_id = lot

        if self.next_step == 'confirm':
            # action_confirm runs the expired-batch check
            res = self.sale_id.with_context(validate_analytic=True).action_confirm()
            return res if isinstance(res, dict) else {'type': 'ir.actions.act_window_close'}
        # A batch entered here with a past expiry date must not be sold either.
        self.sale_id._check_expired_batches()
        return self.sale_id._action_split_payment_wizard()


class SaleMissingBatchWizardLine(models.TransientModel):
    _name = 'sale.missing.batch.wizard.line'
    _description = 'Missing Batch Line'

    wizard_id = fields.Many2one('sale.missing.batch.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Medicine', required=True, readonly=True)
    lot_name = fields.Char(string='Batch No')
    expiration_date = fields.Datetime(string='Expiry Date')
