from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

DOCTOR_GROUP = 'hospital_management.group_hospital_doctor'
MAX_RANGE_DAYS = 731
TOP_DOCTORS = 8
TOP_MEDICINES = 10

STATUS_LABELS = [
    ('draft', 'Draft'),
    ('op', 'OP Generated'),
    ('consulting', 'Consulting'),
    ('pharmacy', 'Pharmacy'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]
GENDER_LABELS = {'male': 'Male', 'female': 'Female', 'other': 'Other'}
MODE_LABELS = {'offline': 'Offline', 'online': 'Online'}
TYPE_LABELS = {'outpatient': 'Out Patient', 'inpatient': 'In Patient'}


class HospitalDoctorDashboard(models.AbstractModel):
    _name = 'hospital.doctor.dashboard'
    _description = 'Clinic Dashboard (Doctors)'

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    def _check_doctor_access(self):
        if not self.env.user.has_group(DOCTOR_GROUP):
            raise AccessError(_("Only doctors can view the clinic dashboard."))

    def _allowed_company_ids(self, company_ids=None):
        """ Requested hospitals (companies), restricted to the user's own. """
        allowed = self.env.user.company_ids.ids
        if company_ids:
            ids = [int(c) for c in company_ids if int(c) in allowed]
            if ids:
                return ids
        return [c for c in self.env.companies.ids if c in allowed] or [self.env.company.id]

    # ------------------------------------------------------------------
    # Public RPC
    # ------------------------------------------------------------------
    @api.model
    def get_filter_options(self):
        self._check_doctor_access()
        user = self.env.user
        companies = user.company_ids
        Employee = self.env['hr.employee'].sudo()
        self.env.cr.execute(
            "SELECT DISTINCT doctor_id FROM hospital_op_ticket WHERE doctor_id IS NOT NULL")
        ticket_doctor_ids = [r[0] for r in self.env.cr.fetchall()]
        doctors = Employee.search([
            ('company_id', 'in', companies.ids),
            '|', ('job_id.name', '=', 'Doctor'), ('id', 'in', ticket_doctor_ids),
        ], order='name')
        my_doctor = doctors.filtered(lambda e: e.user_id == user)[:1]
        return {
            'companies': [{'id': c.id, 'name': c.name} for c in companies.sorted('name')],
            'default_company_ids': self._allowed_company_ids(),
            'doctors': [{'id': d.id, 'name': d.name, 'company_id': d.company_id.id} for d in doctors],
            'my_doctor_id': my_doctor.id or False,
            'currency_id': self.env.company.currency_id.id,
        }

    @api.model
    def get_dashboard_data(self, date_from, date_to, company_ids=None, doctor_id=False):
        self._check_doctor_access()
        d_from = fields.Date.to_date(date_from)
        d_to = fields.Date.to_date(date_to)
        if not d_from or not d_to or d_from > d_to:
            raise UserError(_("Please choose a valid date range."))
        if (d_to - d_from).days > MAX_RANGE_DAYS:
            raise UserError(_("Please choose a date range of at most two years."))
        company_ids = self._allowed_company_ids(company_ids)
        doctor_id = int(doctor_id) if doctor_id else False

        span = (d_to - d_from).days + 1
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=span - 1)

        current = self._collect(d_from, d_to, company_ids, doctor_id, detailed=True)
        previous = self._collect(prev_from, prev_to, company_ids, doctor_id, detailed=False)

        kpis = current.pop('kpis')
        for key in ('visits', 'patients', 'new_patients', 'revenue_total'):
            kpis[key + '_prev'] = previous['kpis'][key]

        currency = self.env['res.company'].browse(company_ids[0]).currency_id
        return {
            'period': {
                'date_from': fields.Date.to_string(d_from),
                'date_to': fields.Date.to_string(d_to),
                'prev_from': fields.Date.to_string(prev_from),
                'prev_to': fields.Date.to_string(prev_to),
                'bucket': current['bucket'],
            },
            'currency_id': currency.id,
            'kpis': kpis,
            **current,
        }

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------
    def _utc_bounds(self, d_from, d_to):
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = tz.localize(datetime.combine(d_from, time.min)).astimezone(pytz.UTC)
        end = tz.localize(datetime.combine(d_to + timedelta(days=1), time.min)).astimezone(pytz.UTC)
        return start.replace(tzinfo=None), end.replace(tzinfo=None)

    @staticmethod
    def _bucket_kind(d_from, d_to):
        span = (d_to - d_from).days + 1
        if span <= 62:
            return 'day'
        if span <= 182:
            return 'week'
        return 'month'

    @staticmethod
    def _bucket_start(day, kind):
        if kind == 'week':
            return day - timedelta(days=day.weekday())
        if kind == 'month':
            return day.replace(day=1)
        return day

    def _buckets(self, d_from, d_to, kind):
        keys, day = [], self._bucket_start(d_from, kind)
        while day <= d_to:
            keys.append(day)
            if kind == 'day':
                day += timedelta(days=1)
            elif kind == 'week':
                day += timedelta(days=7)
            else:
                day = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
        return keys

    @staticmethod
    def _bucket_label(day, kind):
        if kind == 'month':
            return day.strftime('%b %Y')
        if kind == 'week':
            return 'Wk %s' % day.strftime('%d %b')
        return day.strftime('%d %b')

    def _collect(self, d_from, d_to, company_ids, doctor_id, detailed):
        cr = self.env.cr
        tz_name = self.env.user.tz or 'UTC'
        start, end = self._utc_bounds(d_from, d_to)
        doctor_clause = "AND t.doctor_id = %(doctor)s" if doctor_id else ""
        params = {
            'start': start, 'end': end, 'tz': tz_name,
            'companies': company_ids, 'doctor': doctor_id,
            'dfrom': d_from, 'dto': d_to,
        }

        # ---------------- Visits (a visit's hospital is its doctor's company)
        cr.execute(f"""
            SELECT t.id, t.state, t.patient_id, t.doctor_id, t.visit_mode, t.patient_type,
                   (t.appointment_date AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s) AS local_dt,
                   p.gender
              FROM hospital_op_ticket t
              JOIN hr_employee e ON e.id = t.doctor_id
         LEFT JOIN hospital_patient p ON p.id = t.patient_id
             WHERE t.appointment_date >= %(start)s AND t.appointment_date < %(end)s
               AND e.company_id = ANY(%(companies)s)
               {doctor_clause}
        """, params)
        tickets = cr.dictfetchall()
        active = [t for t in tickets if t['state'] != 'cancelled']
        patient_ids = {t['patient_id'] for t in active if t['patient_id']}

        new_patients = 0
        if patient_ids:
            cr.execute("""
                SELECT patient_id, MIN(appointment_date)
                  FROM hospital_op_ticket
                 WHERE patient_id = ANY(%s) AND state != 'cancelled'
              GROUP BY patient_id
            """, [list(patient_ids)])
            new_patients = sum(1 for _pid, first in cr.fetchall() if first and first >= start)

        # ---------------- Revenue (posted customer invoices / refunds)
        doctor_rev_clause = "WHERE COALESCE(ct.doctor_id, base.op_ticket_id_doctor) = %(doctor)s" if doctor_id else ""
        cr.execute(f"""
            WITH mv AS (
                SELECT am.id, am.invoice_date, am.amount_total_signed AS amount,
                       COALESCE(am.reversed_entry_id, am.id) AS base_id
                  FROM account_move am
                 WHERE am.move_type IN ('out_invoice', 'out_refund')
                   AND am.state = 'posted'
                   AND am.invoice_date BETWEEN %(dfrom)s AND %(dto)s
                   AND am.company_id = ANY(%(companies)s)
            )
            SELECT mv.invoice_date, mv.amount,
                   ct.doctor_id IS NOT NULL AS is_consultation,
                   EXISTS (
                       SELECT 1 FROM account_move_line aml
                         JOIN sale_order_line_invoice_rel rel ON rel.invoice_line_id = aml.id
                        WHERE aml.move_id = mv.base_id
                   ) AS is_sale
              FROM mv
              JOIN LATERAL (
                   SELECT ot.doctor_id AS op_ticket_id_doctor
                     FROM account_move b
                LEFT JOIN hospital_op_ticket ot ON ot.id = b.op_ticket_id
                    WHERE b.id = mv.base_id
                   ) base ON TRUE
         LEFT JOIN LATERAL (
                   SELECT doctor_id FROM hospital_op_ticket
                    WHERE consultation_invoice_id = mv.base_id LIMIT 1
                   ) ct ON TRUE
            {doctor_rev_clause}
        """, params)
        invoices = cr.dictfetchall()

        revenue = defaultdict(float)
        for inv in invoices:
            revenue[self._revenue_category(inv)] += inv['amount']
        revenue_total = sum(revenue.values())

        kpis = {
            'visits': len(active),
            'patients': len(patient_ids),
            'new_patients': new_patients,
            'cancelled': len(tickets) - len(active),
            'revenue_total': revenue_total,
            'revenue_consultation': revenue['consultation'],
            'revenue_pharmacy': revenue['pharmacy'],
            'revenue_other': revenue['other'],
            'avg_revenue_per_visit': revenue_total / len(active) if active else 0.0,
        }
        if not detailed:
            return {'kpis': kpis}

        # ---------------- Prescriptions
        ticket_ids = [t['id'] for t in active]
        medicines, with_rx = [], 0
        if ticket_ids:
            cr.execute("""
                SELECT medicine_id, COUNT(*) AS times, COALESCE(SUM(quantity), 0) AS qty
                  FROM prescription_line
                 WHERE op_ticket_id = ANY(%s) AND medicine_id IS NOT NULL
              GROUP BY medicine_id
              ORDER BY times DESC, qty DESC
                 LIMIT %s
            """, [ticket_ids, TOP_MEDICINES])
            rows = cr.fetchall()
            products = self.env['product.product'].sudo().browse([r[0] for r in rows])
            names = {p.id: p.display_name for p in products}
            medicines = [{'name': names.get(pid, ''), 'count': times, 'qty': qty} for pid, times, qty in rows]
            cr.execute("""
                SELECT COUNT(DISTINCT op_ticket_id) FROM prescription_line WHERE op_ticket_id = ANY(%s)
            """, [ticket_ids])
            with_rx = cr.fetchone()[0]
        kpis['prescription_rate'] = with_rx / len(active) if active else 0.0

        # ---------------- Time series
        kind = self._bucket_kind(d_from, d_to)
        keys = self._buckets(d_from, d_to, kind)
        visit_counts = Counter(self._bucket_start(t['local_dt'].date(), kind) for t in active)
        rev_by_bucket = defaultdict(lambda: defaultdict(float))
        for inv in invoices:
            rev_by_bucket[self._bucket_start(inv['invoice_date'], kind)][self._revenue_category(inv)] += inv['amount']
        labels = [self._bucket_label(k, kind) for k in keys]
        visits_series = {'labels': labels, 'values': [visit_counts.get(k, 0) for k in keys]}
        revenue_series = {
            'labels': labels,
            'consultation': [round(rev_by_bucket[k]['consultation'], 2) for k in keys],
            'pharmacy': [round(rev_by_bucket[k]['pharmacy'], 2) for k in keys],
            'other': [round(rev_by_bucket[k]['other'], 2) for k in keys],
        }

        # ---------------- Busiest hours
        hour_counts = Counter(t['local_dt'].hour for t in active if t['local_dt'])
        if hour_counts:
            first, last = min(hour_counts), max(hour_counts)
            hours = list(range(first, last + 1))
        else:
            hours = list(range(8, 21))
        hours_series = {
            'labels': [self._hour_label(h) for h in hours],
            'values': [hour_counts.get(h, 0) for h in hours],
        }

        # ---------------- Visits by doctor
        doctor_counts = Counter(t['doctor_id'] for t in active)
        doctor_names = {
            e.id: e.name for e in self.env['hr.employee'].sudo().browse(list(doctor_counts))
        }
        ranked = doctor_counts.most_common()
        doctors = [{'name': doctor_names.get(did, ''), 'visits': n} for did, n in ranked[:TOP_DOCTORS]]
        rest = sum(n for _did, n in ranked[TOP_DOCTORS:])
        if rest:
            doctors.append({'name': _('Other doctors'), 'visits': rest})

        # ---------------- Status & patient mix
        status_counts = Counter(t['state'] for t in tickets)
        status = [{'key': k, 'label': lbl, 'count': status_counts.get(k, 0)} for k, lbl in STATUS_LABELS]

        def mix(field, labels_map):
            counts = Counter(t[field] for t in active)
            items = [{'label': lbl, 'count': counts.get(k, 0)} for k, lbl in labels_map.items()]
            unknown = sum(n for k, n in counts.items() if k not in labels_map)
            if unknown:
                items.append({'label': _('Not set'), 'count': unknown})
            return items

        return {
            'kpis': kpis,
            'bucket': kind,
            'visits_series': visits_series,
            'revenue_series': revenue_series,
            'hours_series': hours_series,
            'doctors': doctors,
            'medicines': medicines,
            'status': status,
            'mix': {
                'gender': mix('gender', GENDER_LABELS),
                'mode': mix('visit_mode', MODE_LABELS),
                'type': mix('patient_type', TYPE_LABELS),
            },
        }

    @staticmethod
    def _revenue_category(inv):
        if inv['is_consultation']:
            return 'consultation'
        if inv['is_sale']:
            return 'pharmacy'
        return 'other'

    @staticmethod
    def _hour_label(hour):
        suffix = 'am' if hour < 12 else 'pm'
        return '%d%s' % (hour % 12 or 12, suffix)
