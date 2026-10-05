from collections import defaultdict

from odoo import _, api, fields, models

TOP_VENDORS = 8
TOP_PRODUCTS = 10
LIST_LIMIT = 100
# Vendor bills by days past due (negative = not yet due).
AGEING = [
    ('over60', 'Overdue 60+ d', 61, None),
    ('over30', 'Overdue 31–60 d', 31, 60),
    ('over0', 'Overdue 1–30 d', 1, 30),
    ('due7', 'Due within 7 d', -7, 0),
    ('due30', 'Due in 8–30 d', -30, -8),
    ('later', 'Due later', None, -31),
]


class HospitalPurchaseDashboard(models.AbstractModel):
    _name = 'hospital.purchase.dashboard'
    _inherit = 'hospital.dashboard.mixin'
    _description = 'Purchase Dashboard (Doctors)'

    @api.model
    def get_filter_options(self):
        self._check_doctor_access()
        return {'currency_id': self.env.company.currency_id.id}

    @api.model
    def get_dashboard_data(self, date_from, date_to):
        self._check_doctor_access()
        d_from, d_to = self._parse_range(date_from, date_to)
        company_ids = self._allowed_company_ids()
        prev_from, prev_to = self._previous_range(d_from, d_to)

        orders = self._orders(d_from, d_to, company_ids)
        prev_orders = self._orders(prev_from, prev_to, company_ids)
        lines = self._lines([o['id'] for o in orders])
        bills = self._open_bills(company_ids)
        waiting = self._waiting_receipt(company_ids)

        kpis = {
            'spend': sum(o['amount'] for o in orders),
            'spend_prev': sum(o['amount'] for o in prev_orders),
            'orders': len(orders),
            'orders_prev': len(prev_orders),
            'vendors': len({o['partner_id'] for o in orders}),
            'rfqs': self._open_rfqs(company_ids),
            'waiting_receipt': len(waiting),
            'bills_due': sum(b['residual'] for b in bills),
            'overdue': sum(b['residual'] for b in bills if b['days_overdue'] > 0),
            'overdue_count': sum(1 for b in bills if b['days_overdue'] > 0),
        }
        kpis['avg_order'] = kpis['spend'] / kpis['orders'] if kpis['orders'] else 0.0

        currency = self.env['res.company'].browse(company_ids[0]).currency_id
        overdue_rows = [b for b in bills if b['days_overdue'] > 0]
        return {
            'period': {
                'date_from': fields.Date.to_string(d_from),
                'date_to': fields.Date.to_string(d_to),
                'prev_from': fields.Date.to_string(prev_from),
                'prev_to': fields.Date.to_string(prev_to),
                'bucket': self._bucket_kind(d_from, d_to),
            },
            'currency_id': currency.id,
            'kpis': kpis,
            'series': self._series(orders, d_from, d_to),
            'top_vendors': self._top_vendors(orders),
            'top_products': self._top_products(lines),
            'ageing': self._ageing(bills),
            'lists': {
                'overdue': {'rows': overdue_rows[:LIST_LIMIT], 'total': len(overdue_rows)},
                'bills': {'rows': bills[:LIST_LIMIT], 'total': len(bills)},
                'waiting': {'rows': waiting[:LIST_LIMIT], 'total': len(waiting)},
            },
        }

    # ------------------------------------------------------------------
    def _orders(self, d_from, d_to, company_ids):
        """ Confirmed purchase orders, dated by confirmation (or order) date. """
        start, end = self._utc_bounds(d_from, d_to)
        self.env.cr.execute("""
            SELECT po.id, po.partner_id, p.name AS partner_name,
                   COALESCE(po.date_approve, po.date_order) AS order_date,
                   COALESCE(po.amount_total, 0) AS amount
              FROM purchase_order po
              JOIN res_partner p ON p.id = po.partner_id
             WHERE po.state IN ('purchase', 'done')
               AND COALESCE(po.date_approve, po.date_order) >= %s
               AND COALESCE(po.date_approve, po.date_order) < %s
               AND po.company_id = ANY(%s)
        """, [start, end, company_ids])
        return self.env.cr.dictfetchall()

    def _lines(self, order_ids):
        if not order_ids:
            return []
        self.env.cr.execute("""
            SELECT product_id, COALESCE(product_qty, 0) AS qty, COALESCE(price_total, 0) AS amount
              FROM purchase_order_line
             WHERE order_id = ANY(%s) AND product_id IS NOT NULL AND display_type IS NULL
        """, [order_ids])
        return self.env.cr.dictfetchall()

    def _series(self, orders, d_from, d_to):
        kind = self._bucket_kind(d_from, d_to)
        keys = self._buckets(d_from, d_to, kind)
        spend = defaultdict(float)
        for order in orders:
            spend[self._bucket_start(self._to_local_date(order['order_date']), kind)] += order['amount']
        return {
            'labels': [self._bucket_label(k, kind) for k in keys],
            'spend': [round(spend[k], 2) for k in keys],
        }

    def _top_vendors(self, orders):
        totals = defaultdict(lambda: {'amount': 0.0, 'name': ''})
        for order in orders:
            totals[order['partner_id']]['amount'] += order['amount']
            totals[order['partner_id']]['name'] = order['partner_name']
        rows = [{'name': v['name'], 'amount': round(v['amount'], 2)} for v in totals.values()]
        return self._top(rows, 'amount', TOP_VENDORS, _('Other vendors'))

    def _top_products(self, lines):
        totals = defaultdict(lambda: {'amount': 0.0, 'qty': 0.0})
        for line in lines:
            totals[line['product_id']]['amount'] += line['amount']
            totals[line['product_id']]['qty'] += line['qty']
        ranked = sorted(totals.items(), key=lambda kv: -kv[1]['amount'])[:TOP_PRODUCTS]
        products = self.env['product.product'].sudo().browse([pid for pid, _v in ranked])
        names = {p.id: p.display_name for p in products}
        return [{'name': names.get(pid, ''), 'amount': round(v['amount'], 2), 'qty': v['qty']} for pid, v in ranked]

    def _open_rfqs(self, company_ids):
        self.env.cr.execute("""
            SELECT COUNT(*) FROM purchase_order
             WHERE state IN ('draft', 'sent', 'to approve') AND company_id = ANY(%s)
        """, [company_ids])
        return self.env.cr.fetchone()[0]

    def _waiting_receipt(self, company_ids):
        """ Confirmed purchase orders not fully received (as of now). """
        self.env.cr.execute("""
            SELECT po.id, po.name, p.name, po.date_planned, COALESCE(po.amount_total, 0), po.receipt_status
              FROM purchase_order po
              JOIN res_partner p ON p.id = po.partner_id
             WHERE po.state = 'purchase' AND po.receipt_status IN ('pending', 'partial')
               AND po.company_id = ANY(%s)
          ORDER BY po.date_planned NULLS LAST, po.id
        """, [company_ids])
        today = fields.Date.context_today(self)
        rows = []
        for po_id, name, partner, planned, amount, status in self.env.cr.fetchall():
            expected = self._to_local_date(planned) if planned else None
            rows.append({
                'id': po_id, 'name': name, 'partner': partner, 'amount': amount,
                'expected': fields.Date.to_string(expected) if expected else '',
                'late': bool(expected and expected < today),
                'status': _('Partially received') if status == 'partial' else _('Not received'),
            })
        return rows

    def _open_bills(self, company_ids):
        """ Posted vendor bills still to pay (as of now), oldest due first. """
        today = fields.Date.context_today(self)
        self.env.cr.execute("""
            SELECT am.id, am.name, am.ref, p.name, am.invoice_date, am.invoice_date_due,
                   ABS(COALESCE(am.amount_residual_signed, 0))
              FROM account_move am
              JOIN res_partner p ON p.id = am.partner_id
             WHERE am.move_type = 'in_invoice' AND am.state = 'posted'
               AND am.payment_state IN ('not_paid', 'partial')
               AND am.company_id = ANY(%s)
          ORDER BY am.invoice_date_due NULLS LAST, am.id
        """, [company_ids])
        rows = []
        for move_id, name, ref, partner, inv_date, due, residual in self.env.cr.fetchall():
            if not residual:
                continue
            rows.append({
                'id': move_id, 'name': name, 'ref': ref or '', 'partner': partner,
                'date': fields.Date.to_string(inv_date) if inv_date else '',
                'due': fields.Date.to_string(due) if due else '',
                'days_overdue': (today - due).days if due else 0,
                'residual': residual,
            })
        return rows

    @staticmethod
    def _ageing(bills):
        buckets = {key: {'key': key, 'label': label, 'amount': 0.0, 'count': 0} for key, label, *_rest in AGEING}
        for bill in bills:
            days = bill['days_overdue']
            for key, _label, low, high in AGEING:
                if (low is None or days >= low) and (high is None or days <= high):
                    buckets[key]['amount'] += bill['residual']
                    buckets[key]['count'] += 1
                    break
        return [buckets[key] for key, *_rest in AGEING]
