from collections import Counter, defaultdict
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

MAX_RANGE_DAYS = 731
TOP_DOCTORS = 8
TOP_MEDICINES = 10
TOP_PROCEDURES = 10

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
    _inherit = 'hospital.dashboard.mixin'
    _description = 'Clinic Dashboard (Doctors)'

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
            'drill': self._drill_access(['hospital.op.ticket', 'hospital.patient', 'account.move']),
            'currency_id': self.env.company.currency_id.id,
        }

    @api.model
    def get_dashboard_data(self, date_from, date_to, company_ids=None, doctor_id=False):
        self._check_doctor_access()
        # The data below is read with SQL: write pending ORM changes first.
        self.env.flush_all()
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
        for key in ('visits', 'patients', 'new_patients', 'revenue_total', 'procedures', 'procedure_value'):
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

    def _collect(self, d_from, d_to, company_ids, doctor_id, detailed):
        cr = self.env.cr
        tz = self._user_tz()
        start, end = self._utc_bounds(d_from, d_to)
        doctor_clause = "AND t.doctor_id = %(doctor)s" if doctor_id else ""
        params = {
            'start': start, 'end': end,
            'companies': company_ids, 'doctor': doctor_id,
            'dfrom': d_from, 'dto': d_to,
        }

        # ---------------- Visits (a visit's hospital is its doctor's company)
        cr.execute(f"""
            SELECT t.id, t.state, t.patient_id, t.doctor_id, t.visit_mode, t.patient_type,
                   t.appointment_date AS utc_dt,
                   p.gender
              FROM hospital_op_ticket t
              JOIN hr_employee e ON e.id = t.doctor_id
         LEFT JOIN hospital_patient p ON p.id = t.patient_id
             WHERE t.appointment_date >= %(start)s AND t.appointment_date < %(end)s
               AND e.company_id = ANY(%(companies)s)
               {doctor_clause}
        """, params)
        tickets = cr.dictfetchall()
        # Convert in Python: PostgreSQL may not know legacy zone names (e.g. Asia/Calcutta).
        for t in tickets:
            t['local_dt'] = pytz.utc.localize(t['utc_dt']).astimezone(tz).replace(tzinfo=None)
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
                SELECT am.id, am.invoice_date, COALESCE(am.amount_total_signed, 0) AS amount,
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

        # ---------------- Procedures (prescribed on the visits above)
        ticket_ids = [t['id'] for t in active]
        procedure_lines = []
        if ticket_ids:
            cr.execute("""
                SELECT op_ticket_id, product_id, COALESCE(qty, 0) AS qty, COALESCE(subtotal, 0) AS value
                  FROM op_procedure_line
                 WHERE op_ticket_id = ANY(%s) AND product_id IS NOT NULL
            """, [ticket_ids])
            procedure_lines = cr.dictfetchall()
        kpis.update({
            'procedures': len(procedure_lines),
            'procedure_value': sum(line['value'] for line in procedure_lines),
            'procedure_rate': (len({line['op_ticket_id'] for line in procedure_lines}) / len(active)
                               if active else 0.0),
        })
        if not detailed:
            return {'kpis': kpis}

        # ---------------- Prescriptions
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
            medicines = [{'id': pid, 'name': names.get(pid, ''), 'count': times, 'qty': qty} for pid, times, qty in rows]
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
        starts = self._bucket_starts(keys)
        visits_series = {'labels': labels, 'starts': starts, 'values': [visit_counts.get(k, 0) for k in keys]}
        revenue_series = {
            'labels': labels,
            'starts': starts,
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
        doctors = [{'id': did, 'name': doctor_names.get(did, ''), 'visits': n} for did, n in ranked[:TOP_DOCTORS]]
        rest = sum(n for _did, n in ranked[TOP_DOCTORS:])
        if rest:
            doctors.append({'name': _('Other doctors'), 'visits': rest})

        procedures = self._procedure_stats(procedure_lines, active, keys, kind, doctor_names)

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
            'procedures': procedures,
            'status': status,
            'mix': {
                'gender': mix('gender', GENDER_LABELS),
                'mode': mix('visit_mode', MODE_LABELS),
                'type': mix('patient_type', TYPE_LABELS),
            },
        }

    def _procedure_stats(self, lines, active, keys, kind, doctor_names):
        """ Procedure charts: most prescribed, value, over time, by doctor and
        by patient gender. `lines` are the procedure lines of `active` visits. """
        tickets = {t['id']: t for t in active}
        per_product = defaultdict(lambda: {'count': 0, 'qty': 0.0, 'value': 0.0, 'patients': set()})
        over_time, by_doctor, by_gender = Counter(), Counter(), Counter()
        for line in lines:
            ticket = tickets[line['op_ticket_id']]
            row = per_product[line['product_id']]
            row['count'] += 1
            row['qty'] += line['qty']
            row['value'] += line['value']
            row['patients'].add(ticket['patient_id'])
            over_time[self._bucket_start(ticket['local_dt'].date(), kind)] += 1
            by_doctor[ticket['doctor_id']] += 1
            by_gender[ticket['gender'] or 'unset'] += 1

        products = self.env['product.product'].sudo().browse(list(per_product))
        names = {p.id: p.display_name for p in products}
        rows = [{
            'id': pid,
            'name': names.get(pid, ''),
            'count': v['count'],
            'qty': v['qty'],
            'value': round(v['value'], 2),
            'patients': len(v['patients']),
        } for pid, v in per_product.items()]

        doctors = [{'id': did, 'name': doctor_names.get(did) or self.env['hr.employee'].sudo().browse(did).name, 'count': n}
                   for did, n in by_doctor.most_common()]
        gender = [{'label': lbl, 'count': by_gender.get(k, 0)} for k, lbl in GENDER_LABELS.items()]
        if by_gender.get('unset'):
            gender.append({'label': _('Not set'), 'count': by_gender['unset']})
        return {
            'top': sorted(rows, key=lambda r: (-r['count'], -r['value']))[:TOP_PROCEDURES],
            'by_value': sorted(rows, key=lambda r: -r['value'])[:TOP_PROCEDURES],
            'series': {
                'labels': [self._bucket_label(k, kind) for k in keys],
                'starts': self._bucket_starts(keys),
                'values': [over_time.get(k, 0) for k in keys],
            },
            'doctors': self._top(doctors, 'count', TOP_DOCTORS, _('Other doctors')),
            'gender': gender,
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
