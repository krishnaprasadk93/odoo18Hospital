from odoo import models, fields, api
from datetime import timedelta
from odoo.exceptions import UserError


class HospitalRevenueWizard(models.TransientModel):
    _name = 'hospital.revenue.wizard'
    _description = 'Clinic Revenue Report'

    date_range = fields.Selection([
        ('today', 'Today'),
        ('yesterday', 'Yesterday'),
        ('last_30_days', 'Last 30 Days'),
        ('current_month', 'Current Month'),
        ('previous_month', 'Previous Month'),
        ('current_year', 'Current Year'),
        ('custom', 'Custom'),
    ], string='Date Range', required=True, default='today')

    date_from = fields.Date(string='From Date')
    date_to = fields.Date(string='To Date')

    @api.onchange('date_range')
    def _onchange_date_range(self):
        today = fields.Date.today()

        if self.date_range == 'today':
            self.date_from = today
            self.date_to = today

        elif self.date_range == 'yesterday':
            yesterday = today - timedelta(days=1)
            self.date_from = yesterday
            self.date_to = yesterday

        elif self.date_range == 'last_30_days':
            self.date_from = today - timedelta(days=30)
            self.date_to = today

        elif self.date_range == 'current_month':
            self.date_from = today.replace(day=1)
            self.date_to = today

        elif self.date_range == 'previous_month':
            first_day_current_month = today.replace(day=1)
            last_day_previous_month = first_day_current_month - timedelta(days=1)
            first_day_previous_month = last_day_previous_month.replace(day=1)
            self.date_from = first_day_previous_month
            self.date_to = last_day_previous_month

        elif self.date_range == 'current_year':
            self.date_from = today.replace(month=1, day=1)
            self.date_to = today

        elif self.date_range == 'custom':
            # User will manually select dates
            self.date_from = False
            self.date_to = False

    def action_export_excel(self):
        # Validate custom date range
        if self.date_range == 'custom':
            if not self.date_from or not self.date_to:
                raise UserError('Please select both From Date and To Date for custom range.')
            if self.date_from > self.date_to:
                raise UserError('From Date cannot be greater than To Date.')

        return self.env.ref('hospital_revenue_reporting.hospital_revenue_xlsx').report_action(self)
