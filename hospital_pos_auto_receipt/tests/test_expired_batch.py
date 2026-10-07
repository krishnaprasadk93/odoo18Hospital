from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestExpiredBatch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'lot_id' not in cls.env['sale.order.line']._fields or 'expiration_date' not in cls.env['stock.lot']._fields:
            cls.skip = True
            return
        cls.skip = False
        cls.env.company.has_received_warning_stock_sms = True
        now = fields.Datetime.now()
        cls.partner = cls.env['res.partner'].create({'name': 'Expiry Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Expiry Syrup', 'type': 'consu', 'is_storable': True, 'tracking': 'lot', 'list_price': 50,
        })
        cls.expired_lot = cls.env['stock.lot'].create({
            'name': 'OLD-1', 'product_id': cls.product.id, 'expiration_date': now - timedelta(days=3)})
        cls.valid_lot = cls.env['stock.lot'].create({
            'name': 'NEW-1', 'product_id': cls.product.id, 'expiration_date': now + timedelta(days=200)})
        stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.product, stock, 10, lot_id=cls.expired_lot)
        cls.env['stock.quant']._update_available_quantity(cls.product, stock, 10, lot_id=cls.valid_lot)

    def setUp(self):
        super().setUp()
        if self.skip:
            self.skipTest('needs hospital_management (sale line batch) and product_expiry')

    def _order(self, lot=False, product=None):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': (product or self.product).id, 'product_uom_qty': 2,
                                   'lot_id': lot and lot.id})],
        })

    def test_confirm_blocked_for_expired_batch(self):
        order = self._order(self.expired_lot)
        with self.assertRaises(UserError) as err:
            order.action_confirm_check_batch()
        self.assertIn('OLD-1', str(err.exception))
        self.assertIn('expired', str(err.exception))
        self.assertEqual(order.state, 'draft')

    def test_confirm_and_pay_blocked_for_expired_batch(self):
        order = self._order(self.expired_lot)
        with self.assertRaises(UserError):
            order.action_open_split_payment()
        self.assertEqual(order.state, 'draft')

    def test_valid_batch_confirms(self):
        order = self._order(self.valid_lot)
        order.action_confirm_check_batch()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.action_open_split_payment()['res_model'], 'split.payment.wizard')

    def test_all_batches_expired_without_batch_chosen(self):
        product = self.env['product.product'].create({
            'name': 'Only Expired Drops', 'type': 'consu', 'is_storable': True, 'tracking': 'lot'})
        self.env['stock.lot'].create({'name': 'X-1', 'product_id': product.id,
                                      'expiration_date': fields.Datetime.now() - timedelta(days=1)})
        order = self._order(product=product)
        with self.assertRaises(UserError) as err:
            order.action_confirm()
        self.assertIn('all batches have expired', str(err.exception))

    def test_no_batch_chosen_with_valid_batch_confirms(self):
        order = self._order()
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_missing_batch_wizard_rejects_past_expiry(self):
        product = self.env['product.product'].create({
            'name': 'New Tablets', 'type': 'consu', 'is_storable': True, 'tracking': 'lot'})
        order = self._order(product=product)
        wizard = self.env['sale.missing.batch.wizard'].create({
            'sale_id': order.id, 'next_step': 'pay',
            'line_ids': [(0, 0, {'product_id': product.id, 'lot_name': 'PAST-1',
                                 'expiration_date': fields.Datetime.now() - timedelta(days=10)})],
        })
        with self.assertRaises(UserError):
            wizard.action_create_batches()
