from odoo import models, fields, api
from odoo.exceptions import UserError


class MedicinePurchaseWizard(models.TransientModel):
    _name = 'medicine.purchase.wizard'
    _description = 'Medicine Purchase Wizard'

    product_id = fields.Many2one('product.product', required=True)
    quantity = fields.Float(required=True)
    batch_no = fields.Char(required=True)
    selling_price = fields.Float(required=True)
    expiry_date = fields.Date(required=True)

    def action_confirm(self):

        product = self.product_id

        # 1️⃣ Get / Create Vendor
        vendor = self.env['res.partner'].search(
            [('name', '=', 'Medicines'), ('supplier_rank', '>', 0)],
            limit=1
        )

        if not vendor:
            vendor = self.env['res.partner'].create({
                'name': 'Medicines',
                'supplier_rank': 1,
            })

        # 2️⃣ Create Purchase Order
        po = self.env['purchase.order'].create({
            'partner_id': vendor.id,
            'date_order': fields.Datetime.now(),
        })

        # 3️⃣ Add Purchase Line
        self.env['purchase.order.line'].create({
            'order_id': po.id,
            'product_id': product.id,
            'name': product.name,
            'product_qty': self.quantity,
            'price_unit': self.selling_price,
            'date_planned': fields.Datetime.now(),
        })

        po.button_confirm()

        # 4️⃣ Receive Product
        picking = po.picking_ids[0]
        picking.action_assign()

        move_line = picking.move_ids_without_package.move_line_ids

        # Check if batch already exists
        lot = self.env['stock.lot'].search([
            ('name', '=', self.batch_no),
            ('product_id', '=', product.id)
        ], limit=1)

        if not lot:
            lot = self.env['stock.lot'].create({
                'name': self.batch_no,
                'product_id': product.id,
                'standard_price': self.selling_price,
                'selling_price': self.selling_price,
                'expiration_date': self.expiry_date,
            })
        else:
            lot.standard_price = self.selling_price
            lot.selling_price = self.selling_price
            lot.expiration_date = self.expiry_date

        for move in picking.move_ids_without_package:
            move.quantity = self.quantity

        move_line.write({
            'lot_id': lot.id,
            'quantity': self.quantity,
        })

        picking.button_validate()

        # 5️⃣ Update Selling Price
        product.list_price = self.selling_price

        return {'type': 'ir.actions.act_window_close'}
