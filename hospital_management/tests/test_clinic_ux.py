from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.hospital_management.exceptions import ClinicError


@tagged('post_install', '-at_install')
class TestClinicUx(TransactionCase):
    """ Pharmacy queue stock badge and titled clinic messages. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doctor = cls.env['hr.employee'].create({'name': 'Dr. Queue'})
        cls.patient = cls.env['hospital.patient'].create({'name': 'Queue Patient', 'phone': '9000022201'})
        Product = cls.env['product.product']
        cls.stocked = Product.create({'name': 'UX Stocked Tab', 'is_medicine': True, 'medicine_type': 'tablet',
                                      'type': 'consu', 'is_storable': True})
        cls.empty = Product.create({'name': 'UX Empty Tab', 'is_medicine': True, 'medicine_type': 'tablet',
                                    'type': 'consu', 'is_storable': True})
        stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.stocked, stock, 1000)

    def _visit(self, *medicines):
        visit = self.env['hospital.op.ticket'].create({'patient_id': self.patient.id, 'doctor_id': self.doctor.id})
        for medicine in medicines:
            self.env['prescription.line'].create({
                'op_ticket_id': visit.id, 'medicine_id': medicine.id, 'morning_dose': 1, 'evening_dose': 1})
        return visit

    def test_pharmacy_stock_text(self):
        none = self._visit()
        self.assertEqual((none.pharmacy_stock_status, none.pharmacy_stock_text), ('none', 'No medicines'))
        ready = self._visit(self.stocked)
        self.assertEqual((ready.pharmacy_stock_status, ready.pharmacy_stock_text), ('ready', 'All in stock'))
        short = self._visit(self.stocked, self.empty)
        self.assertEqual(short.pharmacy_stock_status, 'low')
        self.assertEqual(short.pharmacy_short_count, 1)
        self.assertEqual(short.pharmacy_stock_text, '1 of 2 short')

    def test_clinic_error_carries_title(self):
        with self.assertRaises(ClinicError) as caught:
            self.env.company._check_hospital_payment_journals([('UPI', 10.0, self.env['account.journal'])])
        self.assertEqual(caught.exception.context['exception_class'], 'clinic_error')
        self.assertEqual(caught.exception.context['title'], 'Payment journal missing')
        self.assertIn('UPI', caught.exception.args[0])
