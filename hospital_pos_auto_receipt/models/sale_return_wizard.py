from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrderReturnWizard(models.TransientModel):
    _name = 'sale.order.return.wizard'
    _description = 'Sales Order Custom Return Wizard'

    order_id = fields.Many2one('sale.order', string='Sales Order', required=True)
    journal_id = fields.Many2one(
        'account.journal',
        string='Payment Journal',
        required=True,
        domain="[('type', 'in', ['bank', 'cash'])]"
    )
    line_ids = fields.One2many('sale.order.return.wizard.line', 'wizard_id', string='Lines')


    def action_process_return(self):
        self.ensure_one()
        return_lines = self.line_ids.filtered(lambda l: l.return_qty > 0)

        if not return_lines:
            raise UserError("Please specify a return quantity greater than 0 for at least one product.")

        order = self.order_id

        # -------------------------------------------------------
        # STEP 1: Warehouse Receipt for Storable Products
        # -------------------------------------------------------
        storable_lines = return_lines.filtered(lambda l: l.product_id.is_storable)
        if storable_lines:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('company_id', '=', order.company_id.id),
            ], limit=1)

            if not picking_type:
                raise UserError("No incoming picking type (Receipts) found for this company.")

            # Use customer location from the original delivery if possible
            customer_location = self.env.ref('stock.stock_location_customers')

            picking = self.env['stock.picking'].create({
                'partner_id': order.partner_id.id,
                'picking_type_id': picking_type.id,
                'origin': f"Return of {order.name}",
                'location_id': customer_location.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'sale_id': order.id,
            })

            for rline in storable_lines:
                self.env['stock.move'].create({
                    'name': rline.product_id.display_name,
                    'product_id': int(rline.product_id.id),
                    'product_uom_qty': float(rline.return_qty),
                    'product_uom': rline.so_line_id.product_uom.id,
                    'picking_id': picking.id,
                    'location_id': customer_location.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'sale_line_id': int(rline.so_line_id.id),
                    'to_refund': True,  # Reduces qty_delivered on SO line automatically
                })

            # Confirm → set quantities → validate
            picking.action_confirm()
            picking.action_assign()  # Reserve moves

            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True

            # Validate without backorder popup
            picking.with_context(skip_backorder=True, immediate_transfer=True).button_validate()

        # -------------------------------------------------------
        # STEP 2: Flush DB so qty_delivered updates are committed
        # before we reduce product_uom_qty
        # -------------------------------------------------------
        self.env.flush_all()
        self.env.invalidate_all()  # Force fresh re-read from DB

        # -------------------------------------------------------
        # STEP 3: Reduce SO Line Ordered Quantity
        # -------------------------------------------------------
        for rline in return_lines:
            so_line = rline.so_line_id
            return_qty = float(rline.return_qty)
            current_ordered = float(so_line.product_uom_qty)
            current_delivered = float(so_line.qty_delivered)

            if return_qty > current_ordered:
                raise UserError(
                    f"Return qty ({return_qty}) cannot exceed ordered qty ({current_ordered}) "
                    f"for {so_line.product_id.display_name}."
                )

            # For service/manual delivery products, reduce delivered qty manually
            if so_line.qty_delivered_method == 'manual':
                new_delivered = max(0.0, current_delivered - return_qty)
                so_line.write({'qty_delivered': new_delivered})
                self.env.flush_all()

            # Now safely reduce ordered qty (delivered is already reduced above)
            new_ordered = current_ordered - return_qty
            so_line.write({'product_uom_qty': new_ordered})

        self.env.flush_all()

        # -------------------------------------------------------
        # STEP 4: Create and Post Credit Note (clean context)
        # -------------------------------------------------------
        move_line_vals = []
        for rline in return_lines:
            move_line_vals.append((0, 0, {
                'product_id': int(rline.product_id.id),
                'quantity': float(rline.return_qty),
                'price_unit': float(rline.so_line_id.price_unit),
                'tax_ids': [(6, 0, list(rline.so_line_id.tax_id.ids))],
                'sale_line_ids': [(4, int(rline.so_line_id.id))],
            }))

        clean_ctx = {
            k: v for k, v in self.env.context.items()
            if not k.startswith('default_')
        }

        credit_note = self.env['account.move'].with_context(clean_ctx).create({
            'move_type': 'out_refund',
            'partner_id': order.partner_id.id,
            'invoice_origin': order.name,
            'invoice_line_ids': move_line_vals,
        })
        credit_note.action_post()

        # -------------------------------------------------------
        # STEP 5: Register and Reconcile Payment
        # -------------------------------------------------------
        payment_register = self.env['account.payment.register'].with_context(
            clean_ctx,
            active_model='account.move',
            active_ids=credit_note.ids,
        ).create({
            'journal_id': self.journal_id.id,
            'payment_date': fields.Date.context_today(self),
            'amount': credit_note.amount_residual,
        })
        payment_register.action_create_payments()

        return {'type': 'ir.actions.act_window_close'}


class SaleOrderReturnWizardLine(models.TransientModel):
    _name = 'sale.order.return.wizard.line'
    _description = 'Sales Order Return Wizard Line'

    wizard_id = fields.Many2one('sale.order.return.wizard', required=True, ondelete='cascade')
    so_line_id = fields.Many2one('sale.order.line', required=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    ordered_qty = fields.Float('Ordered Qty', readonly=True)
    return_qty = fields.Float('Return Qty', default=0.0)
