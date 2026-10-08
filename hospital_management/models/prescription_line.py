from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PrescriptionLine(models.Model):
    _name = 'prescription.line'
    _description = 'Prescription Lines'
    _rec_name = 'medicine_id'

    medicine_id = fields.Many2one('product.product', string='Medicine', required=True,
                                  domain=[('is_medicine', '=', True)])

    # Actual dosage fields (editable)
    morning_dose = fields.Float(string='Morning', default=0, digits=(16, 2))
    afternoon_dose = fields.Float(string='Afternoon', default=0, digits=(16, 2))
    evening_dose = fields.Float(string='Evening', default=0, digits=(16, 2))

    # Display fields with unit (for list view display)
    morning_display = fields.Char(string='Morning', compute='_compute_dose_display',
                                  inverse='_inverse_morning_display', store=True)
    afternoon_display = fields.Char(string='Afternoon', compute='_compute_dose_display',
                                    inverse='_inverse_afternoon_display', store=True)
    evening_display = fields.Char(string='Evening', compute='_compute_dose_display',
                                  inverse='_inverse_evening_display', store=True)

    # Unit of measurement
    dose_unit = fields.Selection([
        ('tablet', 'tab'),
        ('capsule', 'cap'),
        ('ml', 'ml'),
        ('gm', 'gm'),
        ('drops', 'drop'),
        ('unit', 'nos')
    ], string='Unit', compute='_compute_dose_unit', store=True, readonly=False)

    duration_number = fields.Selection(
        [(str(i), str(i)) for i in range(1, 32)],
        string='Duration',
        default='1'
    )
    duration_type = fields.Selection([
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')
    ], string='Duration Type', default='days', required=True)

    instruction = fields.Selection([
        ('before', 'Before Food'),
        ('after', 'After Food'),
        ('with', 'With Food'),
        ('empty', 'Empty Stomach')
    ], string='When to Take', default='after')

    notes = fields.Text(string='Special Instructions')

    quantity = fields.Float(string='Total Quantity', compute='_compute_quantity',
                            store=True, readonly=False, digits=(16, 2))

    op_ticket_id = fields.Many2one('hospital.op.ticket', string='OP Ticket', ondelete='cascade')
    patient_id = fields.Many2one('hospital.patient', string='Patient',
                                 related='op_ticket_id.patient_id', store=True)

    available_qty = fields.Float(string='Available Stock', compute='_compute_available_stock')
    forecasted_qty = fields.Float(string='Forecasted Stock', compute='_compute_available_stock')
    stock_location_id = fields.Many2one('stock.location', string='Stock Location',
                                        compute='_compute_stock_location')
    is_out_of_stock = fields.Boolean(string='Out of Stock', compute='_compute_available_stock')
    stock_status = fields.Char(string='Stock Status', compute='_compute_available_stock')

    dosage_pattern = fields.Char(string='Dosage', compute='_compute_dosage_pattern', store=True)

    # Tablet-friendly entry (display helpers, not stored): +/- step and one-tap
    # dose chips from the medicine (or its type preset), and a stock dot.
    dose_step = fields.Float(string='Dose Step', compute='_compute_dose_entry')
    dose_quick_values = fields.Char(string='Quick Doses', compute='_compute_dose_entry')
    dose_fraction = fields.Boolean(string='Show Fractions', compute='_compute_dose_entry')
    dose_summary = fields.Char(string='Dose', compute='_compute_dose_summary')
    stock_state = fields.Selection([
        ('ok', 'In stock'),
        ('low', 'Low stock'),
        ('out', 'Not enough stock'),
    ], string='Stock', compute='_compute_stock_state')

    @api.depends('medicine_id', 'medicine_id.medicine_type')
    def _compute_dose_unit(self):
        """Auto-set dose unit based on medicine type"""
        for rec in self:
            if rec.medicine_id and rec.medicine_id.medicine_type:
                med_type = rec.medicine_id.medicine_type.lower()

                if med_type in ['tablet', 'capsule']:
                    rec.dose_unit = med_type
                elif med_type in ['syrup', 'kashayam', 'oil', 'lotion', 'serum', 'injection']:
                    rec.dose_unit = 'ml'
                elif med_type == 'drops':
                    rec.dose_unit = 'drops'
                elif med_type in ['choornam', 'powder', 'leham']:
                    rec.dose_unit = 'gm'
                elif med_type in ['ointment', 'cream', 'linament', 'spray', 'soap', 'shampoo']:
                    rec.dose_unit = 'unit'
                else:
                    rec.dose_unit = 'unit'
            else:
                rec.dose_unit = 'unit'

    @api.depends('morning_dose', 'afternoon_dose', 'evening_dose', 'dose_unit')
    def _compute_dose_display(self):
        """Compute display fields with units like '1.00 ml', '0.00 ml', etc."""
        for rec in self:
            unit_label = dict(rec._fields['dose_unit'].selection).get(rec.dose_unit, '')

            rec.morning_display = rec._format_dose_with_unit(rec.morning_dose, unit_label)
            rec.afternoon_display = rec._format_dose_with_unit(rec.afternoon_dose, unit_label)
            rec.evening_display = rec._format_dose_with_unit(rec.evening_dose, unit_label)

    def _inverse_morning_display(self):
        """Parse morning_display back to morning_dose when edited"""
        for rec in self:
            rec.morning_dose = rec._parse_dose_value(rec.morning_display)

    def _inverse_afternoon_display(self):
        """Parse afternoon_display back to afternoon_dose when edited"""
        for rec in self:
            rec.afternoon_dose = rec._parse_dose_value(rec.afternoon_display)

    def _inverse_evening_display(self):
        """Parse evening_display back to evening_dose when edited"""
        for rec in self:
            rec.evening_dose = rec._parse_dose_value(rec.evening_display)

    def _parse_dose_value(self, display_value):
        """Extract numeric value from display string like '1.00 ml' -> 1.0"""
        if not display_value:
            return 0.0
        try:
            # Extract first numeric part
            import re
            match = re.search(r'[\d.]+', str(display_value))
            if match:
                return float(match.group())
        except:
            pass
        return 0.0

    def _format_dose_with_unit(self, dose, unit):
        """Format dose value with unit - always show unit"""
        # Format with 2 decimal places
        formatted = f"{dose:.2f}"

        # Always add unit
        return f"{formatted} {unit}"

    @api.depends('morning_dose', 'afternoon_dose', 'evening_dose', 'dose_unit')
    def _compute_dosage_pattern(self):
        """Display dosage with proper formatting and unit"""
        for rec in self:
            morning = rec._format_dose(rec.morning_dose)
            afternoon = rec._format_dose(rec.afternoon_dose)
            evening = rec._format_dose(rec.evening_dose)

            unit_label = dict(rec._fields['dose_unit'].selection).get(rec.dose_unit, '')

            rec.dosage_pattern = f"{morning}-{afternoon}-{evening} {unit_label}"

    @api.depends('medicine_id', 'medicine_id.medicine_type', 'medicine_id.dose_step',
                 'medicine_id.dose_quick_values')
    def _compute_dose_entry(self):
        Preset = self.env['hospital.dose.preset']
        for rec in self:
            medicine = rec.medicine_id
            med_type = medicine.medicine_type or False
            step, quick = Preset._get_for_type(med_type)
            rec.dose_step = medicine.dose_step or step
            rec.dose_quick_values = medicine.dose_quick_values or quick
            rec.dose_fraction = med_type in ('tablet', 'capsule')

    @api.depends('morning_dose', 'afternoon_dose', 'evening_dose', 'dose_unit', 'dose_fraction')
    def _compute_dose_summary(self):
        """ Screen summary like "1½ – 0 – ½ tab" or "0.3 – 0 – 0.6 ml". """
        for rec in self:
            fmt = rec._format_dose_fraction if rec.dose_fraction else rec._format_dose
            unit_label = dict(rec._fields['dose_unit'].selection).get(rec.dose_unit, '')
            doses = ' – '.join(fmt(d or 0.0) for d in (rec.morning_dose, rec.afternoon_dose, rec.evening_dose))
            rec.dose_summary = f"{doses} {unit_label}".strip()

    def _format_dose_fraction(self, dose):
        """ Tablets / capsules: 0.5 -> ½, 1.5 -> 1½, 0.25 -> ¼; other values as decimals. """
        fractions = {0.25: '¼', 0.5: '½', 0.75: '¾'}
        whole = int(dose)
        part = round(dose - whole, 2)
        if part in fractions:
            return (str(whole) if whole else '') + fractions[part]
        return self._format_dose(dose)

    @api.depends('is_out_of_stock', 'forecasted_qty', 'quantity', 'medicine_id')
    def _compute_stock_state(self):
        for rec in self:
            if not rec.medicine_id:
                rec.stock_state = False
            elif rec.is_out_of_stock:
                rec.stock_state = 'out'
            elif rec.forecasted_qty < rec.quantity * 2:
                rec.stock_state = 'low'
            else:
                rec.stock_state = 'ok'

    def _format_dose(self, dose):
        """Format dose value - remove trailing zeros for decimals"""
        if dose == 0:
            return '0'
        elif dose == int(dose):
            return str(int(dose))
        else:
            return f"{dose:.2f}".rstrip('0').rstrip('.')

    @api.depends(
        'medicine_id',
        'morning_dose',
        'afternoon_dose',
        'evening_dose',
        'duration_number',
        'duration_type'
    )
    def _compute_quantity(self):
        """Calculate quantity: Tablet/Capsule auto-calculate, others default to 1"""
        for rec in self:
            if not rec.medicine_id:
                rec.quantity = 1
                continue

            med_type = (rec.medicine_id.medicine_type or '').lower()

            if med_type in ['tablet', 'capsule']:
                daily_dose = (
                        (rec.morning_dose or 0) +
                        (rec.afternoon_dose or 0) +
                        (rec.evening_dose or 0)
                )

                duration = int(rec.duration_number or 0)

                if rec.duration_type == 'days':
                    total_days = duration
                elif rec.duration_type == 'weeks':
                    total_days = duration * 7
                elif rec.duration_type == 'months':
                    total_days = duration * 30
                else:
                    total_days = 0

                rec.quantity = daily_dose * total_days if daily_dose and total_days else 1
            else:
                if not rec.quantity or rec.quantity == 0:
                    rec.quantity = 1

    @api.constrains('duration_number')
    def _check_duration(self):
        for rec in self:
            duration = int(rec.duration_number or 0)
            if duration < 1 or duration > 31:
                raise UserError(_("Duration must be between 1 and 31"))

    @api.depends('medicine_id')
    def _compute_stock_location(self):
        for rec in self:
            if rec.medicine_id:
                warehouse = self.env['stock.warehouse'].search([
                    ('name', 'ilike', 'pharmacy')
                ], limit=1)

                if not warehouse:
                    warehouse = self.env['stock.warehouse'].search([], limit=1)

                if warehouse:
                    rec.stock_location_id = warehouse.lot_stock_id
                else:
                    rec.stock_location_id = False
            else:
                rec.stock_location_id = False

    @api.depends('medicine_id', 'stock_location_id', 'quantity')
    def _compute_available_stock(self):
        for rec in self:
            if rec.medicine_id and rec.stock_location_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', rec.medicine_id.id),
                    ('location_id', '=', rec.stock_location_id.id)
                ])

                rec.available_qty = sum(quants.mapped('quantity'))
                rec.forecasted_qty = sum(quants.mapped('available_quantity'))
                rec.is_out_of_stock = rec.forecasted_qty < rec.quantity

                if rec.is_out_of_stock:
                    rec.stock_status = f'⚠️ Need: {rec.quantity:.0f}, Available: {rec.forecasted_qty:.0f}'
                elif rec.forecasted_qty < rec.quantity * 2:
                    rec.stock_status = f'⚠️ Low: {rec.forecasted_qty:.0f}'
                else:
                    rec.stock_status = f'✓ Stock: {rec.forecasted_qty:.0f}'
            else:
                rec.available_qty = 0
                rec.forecasted_qty = 0
                rec.is_out_of_stock = True
                rec.stock_status = 'N/A'

    @api.onchange('medicine_id')
    def _onchange_medicine_id(self):
        """Reset doses when medicine changes"""
        if self.medicine_id:
            self.morning_dose = 0
            self.afternoon_dose = 0
            self.evening_dose = 0
