from odoo import _, fields, models
from odoo.addons.hospital_management.exceptions import ClinicError


class OpPrescriptionCopyWizard(models.TransientModel):
    _name = 'op.prescription.copy.wizard'
    _description = 'Copy Prescription from a Previous Visit'

    ticket_id = fields.Many2one('hospital.op.ticket', required=True, readonly=True)
    patient_id = fields.Many2one(related='ticket_id.patient_id')
    visit_id = fields.Many2one(
        'hospital.op.ticket', string='Previous Visit', required=True,
        domain="[('patient_id', '=', patient_id), ('id', '!=', ticket_id), ('prescription_ids', '!=', False)]")
    visit_date = fields.Datetime(related='visit_id.appointment_date', string='Visit Date')
    visit_doctor_id = fields.Many2one(related='visit_id.doctor_id', string='Doctor')
    visit_diagnosis = fields.Text(related='visit_id.reason', string='Diagnosis')
    prescription_ids = fields.One2many(related='visit_id.prescription_ids', string='Prescription')
    replace_existing = fields.Boolean(
        string='Replace current prescription',
        help='Remove the medicines already on this visit before copying. '
             'Otherwise the copied medicines are added to them.')

    def action_copy(self):
        self.ensure_one()
        if self.ticket_id.state != 'consulting':
            raise ClinicError(_('Not in consultation'), _(
                'Prescriptions can only be copied while the visit is in consultation.'))
        copied = self.ticket_id._copy_prescription_from(self.visit_id, replace=self.replace_existing)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Copied %(count)s prescription(s) from visit %(visit)s',
                             count=copied, visit=self.visit_id.visit_no),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
