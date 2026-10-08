from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

DEFAULT_STEP = 0.5
DEFAULT_QUICK = '0.5,1,1.5,2'


def _medicine_types(self):
    return self.env['product.template']._fields['medicine_type'].selection


class HospitalDosePreset(models.Model):
    """ Dose step and quick-dose chips per medicine type (tablet ½ steps, syrup 0.3 ml, ...).
    The doctor can always type any dose; these only drive the +/- buttons and chips. """
    _name = 'hospital.dose.preset'
    _description = 'Dose Preset per Medicine Type'
    _order = 'medicine_type'
    _rec_name = 'medicine_type'

    medicine_type = fields.Selection(_medicine_types, string='Medicine Type', required=True)
    dose_step = fields.Float(string='+/- Step', default=DEFAULT_STEP, digits=(16, 2), required=True,
                             help='How much the + and - buttons change the dose.')
    quick_doses = fields.Char(string='Quick Doses', default=DEFAULT_QUICK,
                              help='Comma-separated doses shown as one-tap chips, e.g. 0.3,0.6,0.9')

    _sql_constraints = [
        ('medicine_type_unique', 'unique(medicine_type)', 'There is already a preset for this medicine type.'),
    ]

    @api.constrains('dose_step', 'quick_doses')
    def _check_values(self):
        for rec in self:
            if rec.dose_step <= 0:
                raise ValidationError(_('The +/- step must be greater than zero.'))
            parse_quick_doses(rec.quick_doses)

    @api.model
    def _get_for_type(self, medicine_type):
        preset = self.search([('medicine_type', '=', medicine_type)], limit=1) if medicine_type else self
        if preset:
            return preset.dose_step, preset.quick_doses or ''
        return DEFAULT_STEP, DEFAULT_QUICK


def parse_quick_doses(text):
    """ '0.3, 0.6,0.9' -> [0.3, 0.6, 0.9]; raises on anything that is not a positive number. """
    values = []
    for part in (text or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            value = float(part)
        except ValueError:
            raise ValidationError(_('Quick doses must be numbers separated by commas, e.g. 0.5,1,1.5'))
        if value <= 0:
            raise ValidationError(_('Quick doses must be greater than zero.'))
        values.append(value)
    return values
