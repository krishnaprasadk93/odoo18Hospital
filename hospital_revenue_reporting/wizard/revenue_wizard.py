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

    @api.model
    def get_revenue_summary(self, date_from, date_to):
        """Read-only JSON summary for the given date range, for the RPC-driven
        dashboard apps. Mirrors the payment-reconciliation logic in
        reports/revenue_xlsx.py (walking matched_credit_ids/matched_debit_ids
        to attribute collections to journals) so the dashboard and the Excel
        export never drift apart — reimplementing that matching in a client
        app would be its own source of bugs.
        """
        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ]
        moves = self.env['account.move'].search(domain, order='invoice_date, name')

        unique_patients = set()
        total_revenue = 0.0
        total_credit_notes = 0.0
        total_consultation = 0.0
        total_medicine = 0.0
        total_procedures = 0.0
        journal_collection = {}
        journal_refunds = {}
        total_collected = 0.0
        total_refunded = 0.0

        for m in moves:
            if m.partner_id:
                unique_patients.add(m.partner_id.id)

            if m.move_type == 'out_invoice':
                total_revenue += m.amount_total
                ticket = m.op_ticket_id
                is_consultation = bool(ticket and ticket.consultation_invoice_id.id == m.id)
                if is_consultation:
                    total_consultation += m.amount_total
                else:
                    for line in m.invoice_line_ids:
                        if line.product_id.is_medicine:
                            total_medicine += line.price_subtotal
                        else:
                            total_procedures += line.price_subtotal
            elif m.move_type == 'out_refund':
                total_credit_notes += m.amount_total

            if m.payment_state in ['paid', 'in_payment']:
                receivable_line = m.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'
                )
                if m.move_type == 'out_invoice':
                    for partial in receivable_line.matched_credit_ids:
                        j_name = partial.credit_move_id.move_id.journal_id.name
                        if j_name:
                            journal_collection[j_name] = journal_collection.get(j_name, 0.0) + partial.amount
                            total_collected += partial.amount
                else:
                    for partial in receivable_line.matched_debit_ids:
                        j_name = partial.debit_move_id.move_id.journal_id.name
                        if j_name:
                            journal_refunds[j_name] = journal_refunds.get(j_name, 0.0) + partial.amount
                            total_refunded += partial.amount

        net_revenue = total_revenue - total_credit_notes
        net_collected = total_collected - total_refunded

        self.env.cr.execute("""
            SELECT to_char(am.invoice_date, 'YYYY-MM') AS month, SUM(am.amount_total) AS total
            FROM account_move am
            WHERE am.move_type = 'out_invoice' AND am.state = 'posted' AND am.op_ticket_id IS NOT NULL
              AND am.invoice_date >= %s AND am.invoice_date <= %s
            GROUP BY month ORDER BY month
        """, (date_from, date_to))
        monthly_trend = [{'month': r[0], 'total': r[1]} for r in self.env.cr.fetchall()]

        self.env.cr.execute("""
            SELECT he.name, SUM(am.amount_total) AS total
            FROM account_move am
            JOIN hospital_op_ticket ht ON am.op_ticket_id = ht.id
            JOIN hr_employee he ON ht.doctor_id = he.id
            WHERE am.move_type = 'out_invoice' AND am.state = 'posted'
              AND am.invoice_date >= %s AND am.invoice_date <= %s
            GROUP BY he.name ORDER BY total DESC LIMIT 10
        """, (date_from, date_to))
        top_doctors = [{'doctor_name': r[0], 'total': r[1]} for r in self.env.cr.fetchall()]

        return {
            'total_revenue': total_revenue,
            'total_credit_notes': total_credit_notes,
            'net_revenue': net_revenue,
            'total_patient_visits': len(unique_patients),
            'total_collected': total_collected,
            'total_refunded': total_refunded,
            'net_collected': net_collected,
            'pending_amount': net_revenue - net_collected,
            'total_consultation': total_consultation,
            'total_medicine': total_medicine,
            'total_procedures': total_procedures,
            'journal_collection': journal_collection,
            'journal_refunds': journal_refunds,
            'monthly_trend': monthly_trend,
            'top_doctors': top_doctors,
        }
