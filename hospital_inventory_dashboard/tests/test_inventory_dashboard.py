from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestInventoryDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['hospital.inventory.dashboard']
        cls.pharmacist = new_test_user(
            cls.env, login='inv_pharmacist', tz='UTC',
            groups='base.group_user,hospital_management.group_hospital_pharmacist')
        cls.doctor = new_test_user(
            cls.env, login='inv_doctor', tz='UTC',
            groups='base.group_user,hospital_management.group_hospital_doctor')
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        Product = cls.env['product.product']
        Quant = cls.env['stock.quant']
        now = fields.Datetime.now()

        # Medicines are lot-tracked automatically by hospital_management.
        cls.no_batch = Product.create({'name': 'INV No Batch', 'is_medicine': True})
        cls.untracked = Product.create({'name': 'INV Untracked', 'is_medicine': True})
        lot_u = cls.env['stock.lot'].create({'name': 'U1', 'product_id': cls.untracked.id})
        Quant._update_available_quantity(cls.untracked, cls.stock, 4, lot_id=lot_u)
        Quant._update_available_quantity(cls.untracked, cls.stock, 3)  # stock without a batch

        cls.expiring = Product.create({'name': 'INV Expiring', 'is_medicine': True, 'standard_price': 10})
        lot_soon = cls.env['stock.lot'].create({'name': 'E1', 'product_id': cls.expiring.id,
                                                'expiration_date': now + timedelta(days=20)})
        lot_old = cls.env['stock.lot'].create({'name': 'E0', 'product_id': cls.expiring.id,
                                               'expiration_date': now - timedelta(days=5)})
        Quant._update_available_quantity(cls.expiring, cls.stock, 6, lot_id=lot_soon)
        Quant._update_available_quantity(cls.expiring, cls.stock, 2, lot_id=lot_old)

        cls.negative = Product.create({'name': 'INV Negative', 'is_medicine': True})
        lot_n = cls.env['stock.lot'].create({'name': 'N1', 'product_id': cls.negative.id})
        Quant._update_available_quantity(cls.negative, cls.stock, -3, lot_id=lot_n)

        cls.low = Product.create({'name': 'INV Low', 'is_medicine': True, 'minimum_qty': 10})
        lot_l = cls.env['stock.lot'].create({'name': 'L1', 'product_id': cls.low.id})
        Quant._update_available_quantity(cls.low, cls.stock, 4, lot_id=lot_l)

        cls.today = fields.Date.to_string(fields.Date.today())

    def _data(self, user=None):
        return self.Dashboard.with_user(user or self.pharmacist).get_dashboard_data(
            self.today, self.today, self.warehouse.id, 'medicine')

    @staticmethod
    def _names(data, key):
        return {r['name']: r for r in data['lists'][key]['rows']}

    def test_access(self):
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(self.doctor).get_filter_options()
        with self.assertRaises(AccessError):
            self._data(self.doctor)
        options = self.Dashboard.with_user(self.pharmacist).get_filter_options()
        self.assertIn(self.warehouse.id, [w['id'] for w in options['warehouses']])

    def test_medicines_without_batch(self):
        rows = self._names(self._data(), 'no_batch')
        self.assertEqual(rows['INV No Batch']['issue'], 'No batch created')
        self.assertEqual(rows['INV No Batch']['batches'], 0)
        self.assertEqual(rows['INV Untracked']['issue'], 'Stock without batch')
        self.assertEqual(rows['INV Untracked']['untracked'], 3)
        self.assertNotIn('INV Expiring', rows)

    def test_expiry_negative_low(self):
        data = self._data()
        batches = [r['batch'] for r in data['lists']['expiring']['rows'] if r['name'] == 'INV Expiring']
        self.assertEqual(batches, ['E0', 'E1'])  # expired first, then soonest
        rows = {r['batch']: r for r in data['lists']['expiring']['rows'] if r['name'] == 'INV Expiring'}
        self.assertEqual((rows['E0']['qty'], rows['E0']['value']), (2, 20))
        self.assertLess(rows['E0']['days'], 0)
        self.assertEqual(rows['E1']['qty'], 6)
        buckets = {b['key']: b for b in data['expiry_chart']}
        self.assertGreaterEqual(buckets['expired']['qty'], 2)
        self.assertGreaterEqual(buckets['30']['qty'], 6)
        self.assertEqual(self._names(data, 'negative')['INV Negative']['qty'], -3)
        low = self._names(data, 'low')
        self.assertEqual(low['INV Low']['status'], 'low')
        self.assertEqual(low['INV Low']['shortage'], 6)
        self.assertEqual(low['INV No Batch']['status'], 'out')
        self.assertGreaterEqual(data['kpis']['negative'], 1)
        self.assertGreaterEqual(data['kpis']['expired'], 1)

    def test_legacy_timezone_name(self):
        # Browsers may report the legacy name, which PostgreSQL may not know.
        self.pharmacist.tz = 'Asia/Calcutta'
        self.assertIn('movements', self._data())

    def test_null_quantities(self):
        # Imported / adjusted data can leave NULL quantities and minimums.
        self.env.cr.execute("""
            INSERT INTO stock_quant (product_id, location_id, company_id, quantity, reserved_quantity, in_date)
            VALUES (%s, %s, %s, NULL, 0, now())
        """, [self.untracked.id, self.stock.id, self.env.company.id])
        self.env.cr.execute("UPDATE product_template SET minimum_qty = NULL WHERE id = %s",
                            [self.low.product_tmpl_id.id])
        self.env.invalidate_all()
        rows = self._names(self._data(), 'no_batch')
        self.assertEqual(rows['INV Untracked']['untracked'], 3)
