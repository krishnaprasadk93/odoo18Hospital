from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestPrescriptionEntry(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doctor = cls.env['hr.employee'].create({'name': 'Dr. Tablet'})
        cls.other_doctor = cls.env['hr.employee'].create({'name': 'Dr. Other'})
        cls.patients = cls.env['hospital.patient'].create([
            {'name': f'Tab Patient {i}', 'phone': f'90000111{i:02d}'} for i in range(4)])
        Product = cls.env['product.product']
        cls.tablet = Product.create({'name': 'Tab Para', 'is_medicine': True, 'medicine_type': 'tablet'})
        cls.syrup = Product.create({'name': 'Tab Syrup', 'is_medicine': True, 'medicine_type': 'syrup'})
        cls.cream = Product.create({'name': 'Tab Cream', 'is_medicine': True, 'medicine_type': 'cream',
                                    'dose_step': 2, 'dose_quick_values': '2,4'})

    def _visit(self, patient, doctor=None, minutes_ago=30, **vals):
        return self.env['hospital.op.ticket'].create({
            'patient_id': patient.id,
            'doctor_id': (doctor or self.doctor).id,
            'appointment_date': fields.Datetime.now() - timedelta(minutes=minutes_ago),
            **vals,
        })

    def _line(self, visit, medicine, m=0.0, a=0.0, e=0.0):
        return self.env['prescription.line'].create({
            'op_ticket_id': visit.id, 'medicine_id': medicine.id,
            'morning_dose': m, 'afternoon_dose': a, 'evening_dose': e,
        })

    def test_dose_entry_from_type_preset_and_override(self):
        visit = self._visit(self.patients[0])
        tab = self._line(visit, self.tablet)
        syr = self._line(visit, self.syrup)
        cream = self._line(visit, self.cream)
        self.assertEqual((tab.dose_step, tab.dose_quick_values, tab.dose_fraction), (0.5, '0.5,1,1.5,2', True))
        self.assertEqual(syr.dose_step, 0.3)
        self.assertIn('0.3,0.6,0.9', syr.dose_quick_values)
        self.assertFalse(syr.dose_fraction)
        # the medicine's own values win over its type preset
        self.assertEqual((cream.dose_step, cream.dose_quick_values), (2.0, '2,4'))

    def test_dose_summary_keeps_any_typed_value(self):
        visit = self._visit(self.patients[0])
        tab = self._line(visit, self.tablet, 1.5, 0, 0.5)
        self.assertEqual(tab.dose_summary, '1½ – 0 – ½ tab')
        odd = self._line(visit, self.tablet, 1.2, 0.25, 0)
        self.assertEqual(odd.dose_summary, '1.2 – ¼ – 0 tab')
        syr = self._line(visit, self.syrup, 0.3, 0, 0.6)
        self.assertEqual(syr.dose_summary, '0.3 – 0 – 0.6 ml')
        # the stored pattern (pharmacy / print) is unchanged
        self.assertEqual(tab.dosage_pattern, '1.5-0-0.5 tab')

    def test_quick_doses_validation(self):
        with self.assertRaises(ValidationError):
            self.env['hospital.dose.preset'].search([('medicine_type', '=', 'tablet')]).quick_doses = '1,abc'
        with self.assertRaises(ValidationError):
            self.tablet.product_tmpl_id.dose_quick_values = '0,1'

    def test_next_patient_lowest_waiting_token_same_doctor(self):
        current = self._visit(self.patients[0], state='pharmacy', token_number='001')
        later = self._visit(self.patients[1], state='consulting', consulting_state='started', token_number='003')
        first = self._visit(self.patients[2], state='consulting', consulting_state='started', token_number='002')
        self._visit(self.patients[3], doctor=self.other_doctor, state='consulting',
                    consulting_state='started', token_number='001')
        action = current.action_next_patient()
        self.assertEqual(action['res_model'], 'hospital.op.ticket')
        self.assertEqual(action['res_id'], first.id)
        first.write({'state': 'pharmacy'})
        self.assertEqual(current.action_next_patient()['res_id'], later.id)
        later.write({'state': 'done'})
        self.assertEqual(current.action_next_patient()['tag'], 'display_notification')

    def test_quick_medicines_doctor_first(self):
        for i in range(3):
            self._line(self._visit(self.patients[i]), self.syrup)
        self._line(self._visit(self.patients[0]), self.tablet)
        self._line(self._visit(self.patients[1], doctor=self.other_doctor), self.cream)
        visit = self._visit(self.patients[3])
        quick = visit.get_quick_medicines(limit=10)
        ids = [m['id'] for m in quick]
        self.assertEqual(ids[:2], [self.syrup.id, self.tablet.id])
        # topped up with the clinic's other medicines, after the doctor's own
        self.assertGreater(len(ids), 2)
        self.assertNotIn(self.cream.id, ids[:2])
