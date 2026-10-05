from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestPurchaseDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['hospital.purchase.dashboard']
        cls.doctor = new_test_user(cls.env, login='purch_doctor', tz='UTC',
                                   groups='base.group_user,hospital_management.group_hospital_doctor')
        cls.pharmacist = new_test_user(cls.env, login='purch_pharma', tz='UTC',
                                       groups='base.group_user,hospital_management.group_hospital_pharmacist')
        cls.vendor = cls.env['res.partner'].create({'name': 'Dash Vendor'})
        cls.product = cls.env['product.product'].create({'name': 'Dash Supply', 'type': 'consu', 'is_storable': True})
        cls.po = cls.env['purchase.order'].create({
            'partner_id': cls.vendor.id,
            'order_line': [(0, 0, {'product_id': cls.product.id, 'product_qty': 10, 'price_unit': 100000, 'taxes_id': [(6, 0, [])]})],
        })
        cls.po.button_confirm()
        today = fields.Date.today()
        cls.bill = cls.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': cls.vendor.id,
            'invoice_date': today - timedelta(days=45), 'invoice_date_due': today - timedelta(days=40),
            'invoice_line_ids': [(0, 0, {'name': 'Old supplies', 'quantity': 1, 'price_unit': 500, 'tax_ids': [(6, 0, [])]})],
        })
        cls.bill.action_post()
        cls.today = fields.Date.to_string(today)

    def test_access(self):
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(self.pharmacist).get_dashboard_data(self.today, self.today)
        self.Dashboard.with_user(self.doctor).get_filter_options()

    def test_purchase_numbers(self):
        data = self.Dashboard.with_user(self.doctor).get_dashboard_data(self.today, self.today)
        self.assertIn('Dash Vendor', [v['name'] for v in data['top_vendors']])
        self.assertGreaterEqual(data['kpis']['spend'], 1000000)
        waiting = {r['name']: r for r in data['lists']['waiting']['rows']}
        self.assertEqual(waiting[self.po.name]['status'], 'Not received')
        overdue = {r['id']: r for r in data['lists']['overdue']['rows']}
        self.assertEqual(overdue[self.bill.id]['days_overdue'], 40)
        self.assertEqual(overdue[self.bill.id]['residual'], 500)
        ageing = {b['key']: b for b in data['ageing']}
        self.assertGreaterEqual(ageing['over30']['amount'], 500)
