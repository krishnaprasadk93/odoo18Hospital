from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestDoctorDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['hospital.doctor.dashboard']
        cls.doctor_user = new_test_user(
            cls.env, login='dash_doctor', tz='UTC',
            groups='base.group_user,hospital_management.group_hospital_doctor')
        cls.reception_user = new_test_user(
            cls.env, login='dash_reception', tz='UTC',
            groups='base.group_user,hospital_management.group_hospital_receptionist')
        cls.doctor = cls.env['hr.employee'].create({'name': 'Dr Dash', 'user_id': cls.doctor_user.id})
        partner = cls.env['res.partner'].create({'name': 'Dash Patient', 'phone': '9000000001'})
        cls.patient = cls.env['hospital.patient'].create({'partner_id': partner.id, 'gender': 'female'})
        now = fields.Datetime.now()
        Ticket = cls.env['hospital.op.ticket']
        cls.tickets = Ticket.create([
            {'patient_id': cls.patient.id, 'doctor_id': cls.doctor.id, 'appointment_date': now},
            {'patient_id': cls.patient.id, 'doctor_id': cls.doctor.id, 'appointment_date': now},
            {'patient_id': cls.patient.id, 'doctor_id': cls.doctor.id, 'appointment_date': now,
             'state': 'cancelled'},
        ])
        cls.today = fields.Date.to_string(fields.Date.today())

    def test_only_doctors_can_view(self):
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(self.reception_user).get_filter_options()
        with self.assertRaises(AccessError):
            self.Dashboard.with_user(self.reception_user).get_dashboard_data(self.today, self.today)
        options = self.Dashboard.with_user(self.doctor_user).get_filter_options()
        self.assertEqual(options['my_doctor_id'], self.doctor.id)
        # Click-through only to records the user may open.
        self.assertTrue(options['drill']['hospital.op.ticket'])
        self.assertIn('account.move', options['drill'])

    def test_visit_counts(self):
        data = self.Dashboard.with_user(self.doctor_user).get_dashboard_data(
            self.today, self.today, doctor_id=self.doctor.id)
        kpis = data['kpis']
        self.assertEqual(kpis['visits'], 2)
        self.assertEqual(kpis['cancelled'], 1)
        self.assertEqual(kpis['patients'], 1)
        self.assertEqual(kpis['new_patients'], 1)
        self.assertEqual(sum(data['visits_series']['values']), 2)
        self.assertEqual(data['doctors'], [{'id': self.doctor.id, 'name': 'Dr Dash', 'visits': 2}])
        gender = {g['label']: g['count'] for g in data['mix']['gender']}
        self.assertEqual(gender['Female'], 2)

    def test_previous_period_and_buckets(self):
        start = fields.Date.today() - timedelta(days=99)
        data = self.Dashboard.with_user(self.doctor_user).get_dashboard_data(
            fields.Date.to_string(start), self.today, doctor_id=self.doctor.id)
        self.assertEqual(data['period']['bucket'], 'week')
        self.assertEqual(data['kpis']['visits_prev'], 0)
        self.assertEqual(sum(data['visits_series']['values']), 2)

    def test_legacy_timezone_name(self):
        # Browsers may report the legacy name, which PostgreSQL may not know.
        self.doctor_user.tz = 'Asia/Calcutta'
        data = self.Dashboard.with_user(self.doctor_user).get_dashboard_data(
            self.today, self.today, doctor_id=self.doctor.id)
        self.assertEqual(data['kpis']['visits'], 2)

    def test_procedures(self):
        procedure = self.env['product.product'].create({
            'name': 'Dash Dressing', 'type': 'service', 'is_procedure': True, 'list_price': 150})
        first, second = self.tickets[:2]
        self.env['op.procedure.line'].create([
            {'op_ticket_id': first.id, 'product_id': procedure.id, 'qty': 2, 'price_unit': 150},
            {'op_ticket_id': second.id, 'product_id': procedure.id, 'qty': 1, 'price_unit': 150},
        ])
        # Procedures on a cancelled visit are not counted.
        self.env['op.procedure.line'].create(
            {'op_ticket_id': self.tickets[2].id, 'product_id': procedure.id, 'qty': 5, 'price_unit': 150})
        data = self.Dashboard.with_user(self.doctor_user).get_dashboard_data(
            self.today, self.today, doctor_id=self.doctor.id)
        kpis = data['kpis']
        self.assertEqual(kpis['procedures'], 2)
        self.assertEqual(kpis['procedure_value'], 450)
        self.assertEqual(kpis['procedure_rate'], 1.0)
        self.assertEqual(kpis['procedures_prev'], 0)
        top = data['procedures']['top'][0]
        self.assertEqual((top['name'], top['count'], top['qty'], top['patients'], top['value']),
                         ('Dash Dressing', 2, 3, 1, 450))
        self.assertEqual(sum(data['procedures']['series']['values']), 2)
        self.assertEqual(data['procedures']['doctors'], [{'id': self.doctor.id, 'name': 'Dr Dash', 'count': 2}])
        self.assertEqual(data['procedures']['top'][0]['id'], procedure.id)
        self.assertEqual(len(data['procedures']['series']['starts']), len(data['procedures']['series']['labels']))
        gender = {g['label']: g['count'] for g in data['procedures']['gender']}
        self.assertEqual(gender['Female'], 2)
