from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestSaleAllowNegative(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.partner = cls.env['res.partner'].create({'name': 'Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Storable No Stock',
            'type': 'consu',
            'is_storable': True,
        })

    def _create_so(self, qty=5):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
            })],
        })

    def test_delivery_ready_and_negative(self):
        self.env.company.sale_allow_negative_stock = True
        so = self._create_so()
        so.action_confirm()
        picking = so.picking_ids
        self.assertEqual(picking.state, 'assigned')
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(so.order_line.qty_delivered, 5)
        self.assertEqual(self.product.with_context(
            warehouse_id=self.warehouse.id).qty_available, -5)

    def test_disabled_keeps_waiting(self):
        self.env.company.sale_allow_negative_stock = False
        so = self._create_so()
        so.action_confirm()
        self.assertEqual(so.picking_ids.state, 'confirmed')
