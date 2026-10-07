from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestSalesDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['hospital.sales.dashboard']
        cls.doctor = new_test_user(cls.env, login='sales_doctor', tz='UTC',
                                   groups='base.group_user,hospital_management.group_hospital_doctor')
        cls.pharmacist = new_test_user(cls.env, login='sales_pharma', tz='UTC',
                                       groups='base.group_user,hospital_management.group_hospital_pharmacist')
        cls.partner = cls.env['res.partner'].create({'name': 'Sales Dash Customer'})
        cls.service = cls.env['product.product'].create({'name': 'Dash Service', 'type': 'service', 'list_price': 150})
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'order_line': [(0, 0, {'product_id': cls.service.id, 'product_uom_qty': 2, 'price_unit': 500000, 'tax_id': [(6, 0, [])]})],
        })
        cls.order.action_confirm()
        cls.today = fields.Date.to_string(fields.Date.today())

    def test_access(self):
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(self.pharmacist).get_dashboard_data(self.today, self.today)
        self.Dashboard.with_user(self.doctor).get_filter_options()

    def test_sales_totals(self):
        data = self.Dashboard.with_user(self.doctor).get_dashboard_data(self.today, self.today, 'otc')
        self.assertIn('Sales Dash Customer', [c['name'] for c in data['top_customers']])
        self.assertIn('Dash Service', [p['name'] for p in data['top_products']])
        self.assertGreaterEqual(data['kpis']['sales'], 1000000)
        self.assertEqual(sum(data['series']['otc']), data['kpis']['sales'])
        self.assertEqual(sum(data['series']['op']), 0)
        op = self.Dashboard.with_user(self.doctor).get_dashboard_data(self.today, self.today, 'op')
        self.assertNotIn('Sales Dash Customer', [c['name'] for c in op['top_customers']])
        # Click-through data: row ids and bucket start dates.
        customer = next(c for c in data['top_customers'] if c['name'] == 'Sales Dash Customer')
        self.assertEqual(customer['id'], self.partner.id)
        self.assertEqual(len(data['series']['starts']), len(data['series']['labels']))
        self.assertTrue(self.Dashboard.with_user(self.doctor).get_filter_options()['drill'] is not None)
        to_invoice = [r['name'] for r in data['lists']['to_invoice']['rows']]
        self.assertIn(self.order.name, to_invoice)
