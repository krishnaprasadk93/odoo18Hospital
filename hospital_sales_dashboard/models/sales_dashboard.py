from collections import defaultdict

from odoo import _, api, fields, models

TOP_PRODUCTS = 10
TOP_CUSTOMERS = 8
LIST_LIMIT = 100
ORDER_TYPES = ('all', 'op', 'otc')


class HospitalSalesDashboard(models.AbstractModel):
    _name = 'hospital.sales.dashboard'
    _inherit = 'hospital.dashboard.mixin'
    _description = 'Sales Dashboard (Doctors)'

    @api.model
    def get_filter_options(self):
        self._check_doctor_access()
        return {'currency_id': self.env.company.currency_id.id}

    @api.model
    def get_dashboard_data(self, date_from, date_to, order_type='all'):
        self._check_doctor_access()
        d_from, d_to = self._parse_range(date_from, date_to)
        order_type = order_type if order_type in ORDER_TYPES else 'all'
        company_ids = self._allowed_company_ids()
        prev_from, prev_to = self._previous_range(d_from, d_to)

        orders = self._orders(d_from, d_to, company_ids, order_type)
        prev_orders = self._orders(prev_from, prev_to, company_ids, order_type)
        order_ids = [o['id'] for o in orders]
        lines = self._lines(order_ids)

        kpis = {
            'sales': sum(o['amount'] for o in orders),
            'sales_prev': sum(o['amount'] for o in prev_orders),
            'orders': len(orders),
            'orders_prev': len(prev_orders),
            'customers': len({o['partner_id'] for o in orders}),
            'items': sum(line['qty'] for line in lines),
            'refunds': self._refunds(d_from, d_to, company_ids),
            'to_invoice': sum(1 for o in orders if o['invoice_status'] == 'to invoice'),
        }
        kpis['avg_order'] = kpis['sales'] / kpis['orders'] if kpis['orders'] else 0.0
        unpaid = self._unpaid_invoices(company_ids)
        kpis['unpaid'] = sum(r['residual'] for r in unpaid)
        kpis['overdue'] = sum(r['residual'] for r in unpaid if r['days_overdue'] > 0)

        currency = self.env['res.company'].browse(company_ids[0]).currency_id
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
            'top_products': self._top_products(lines),
            'top_customers': self._top_customers(orders),
            'payments': self._payments(d_from, d_to, company_ids),
            'lists': {
                'unpaid': {'rows': unpaid[:LIST_LIMIT], 'total': len(unpaid)},
                'to_invoice': self._to_invoice_rows(orders),
            },
        }

    # ------------------------------------------------------------------
    def _orders(self, d_from, d_to, company_ids, order_type):
        start, end = self._utc_bounds(d_from, d_to)
        type_clause = {
            'op': 'AND so.op_ticket_id IS NOT NULL',
            'otc': 'AND so.op_ticket_id IS NULL',
        }.get(order_type, '')
        self.env.cr.execute(f"""
            SELECT so.id, so.name, so.partner_id, so.date_order, so.invoice_status,
                   COALESCE(so.amount_total, 0) AS amount, so.op_ticket_id IS NOT NULL AS is_op,
                   p.name AS partner_name
              FROM sale_order so
              JOIN res_partner p ON p.id = so.partner_id
             WHERE so.state IN ('sale', 'done')
               AND so.date_order >= %s AND so.date_order < %s
               AND so.company_id = ANY(%s)
               {type_clause}
        """, [start, end, company_ids])
        return self.env.cr.dictfetchall()

    def _lines(self, order_ids):
        if not order_ids:
            return []
        self.env.cr.execute("""
            SELECT sol.product_id, COALESCE(sol.product_uom_qty, 0) AS qty,
                   COALESCE(sol.price_total, 0) AS amount
              FROM sale_order_line sol
             WHERE sol.order_id = ANY(%s) AND sol.product_id IS NOT NULL
               AND sol.display_type IS NULL
        """, [order_ids])
        return self.env.cr.dictfetchall()

    def _series(self, orders, d_from, d_to):
        kind = self._bucket_kind(d_from, d_to)
        keys = self._buckets(d_from, d_to, kind)
        op, otc = defaultdict(float), defaultdict(float)
        for order in orders:
            bucket = self._bucket_start(self._to_local_date(order['date_order']), kind)
            (op if order['is_op'] else otc)[bucket] += order['amount']
        return {
            'labels': [self._bucket_label(k, kind) for k in keys],
            'op': [round(op[k], 2) for k in keys],
            'otc': [round(otc[k], 2) for k in keys],
        }

    def _top_products(self, lines):
        totals = defaultdict(lambda: {'amount': 0.0, 'qty': 0.0})
        for line in lines:
            totals[line['product_id']]['amount'] += line['amount']
            totals[line['product_id']]['qty'] += line['qty']
        ranked = sorted(totals.items(), key=lambda kv: -kv[1]['amount'])[:TOP_PRODUCTS]
        products = self.env['product.product'].sudo().browse([pid for pid, _v in ranked])
        names = {p.id: p.display_name for p in products}
        return [{'name': names.get(pid, ''), 'amount': round(v['amount'], 2), 'qty': v['qty']} for pid, v in ranked]

    def _top_customers(self, orders):
        totals = defaultdict(lambda: {'amount': 0.0, 'orders': 0, 'name': ''})
        for order in orders:
            row = totals[order['partner_id']]
            row['amount'] += order['amount']
            row['orders'] += 1
            row['name'] = order['partner_name']
        rows = [{'name': v['name'], 'amount': round(v['amount'], 2), 'orders': v['orders']} for v in totals.values()]
        return self._top(rows, 'amount', TOP_CUSTOMERS, _('Other customers'))

    def _refunds(self, d_from, d_to, company_ids):
        self.env.cr.execute("""
            SELECT COALESCE(SUM(ABS(amount_total_signed)), 0)
              FROM account_move
             WHERE move_type = 'out_refund' AND state = 'posted'
               AND invoice_date BETWEEN %s AND %s AND company_id = ANY(%s)
        """, [d_from, d_to, company_ids])
        return self.env.cr.fetchone()[0]

    def _payments(self, d_from, d_to, company_ids):
        """ Customer payments received in the period, by journal (Cash, Card, UPI...). """
        self.env.cr.execute("""
            SELECT j.id, j.name, COALESCE(SUM(p.amount_company_currency_signed), 0), COUNT(*)
              FROM account_payment p
              JOIN account_journal j ON j.id = p.journal_id
             WHERE p.payment_type = 'inbound' AND p.partner_type = 'customer'
               AND p.state NOT IN ('draft', 'canceled', 'rejected')
               AND p.date BETWEEN %s AND %s AND p.company_id = ANY(%s)
          GROUP BY j.id, j.name
          ORDER BY 3 DESC
        """, [d_from, d_to, company_ids])
        rows = []
        for _jid, name, amount, count in self.env.cr.fetchall():
            label = name.get(self.env.lang) or name.get('en_US') or next(iter(name.values()), '') if isinstance(name, dict) else name
            rows.append({'name': label, 'amount': round(amount, 2), 'count': count})
        return rows

    def _unpaid_invoices(self, company_ids):
        """ Open customer invoices as of today (not limited to the period). """
        today = fields.Date.context_today(self)
        self.env.cr.execute("""
            SELECT am.id, am.name, p.name, am.invoice_date, am.invoice_date_due,
                   COALESCE(am.amount_residual_signed, 0)
              FROM account_move am
              JOIN res_partner p ON p.id = am.partner_id
             WHERE am.move_type = 'out_invoice' AND am.state = 'posted'
               AND am.payment_state IN ('not_paid', 'partial')
               AND am.company_id = ANY(%s)
          ORDER BY am.invoice_date_due NULLS LAST, am.id
        """, [company_ids])
        rows = []
        for move_id, name, partner, inv_date, due, residual in self.env.cr.fetchall():
            if not residual:
                continue
            rows.append({
                'id': move_id,
                'name': name,
                'partner': partner,
                'date': fields.Date.to_string(inv_date) if inv_date else '',
                'due': fields.Date.to_string(due) if due else '',
                'days_overdue': (today - due).days if due else 0,
                'residual': residual,
            })
        return rows

    @staticmethod
    def _to_invoice_rows(orders):
        rows = [
            {'id': o['id'], 'name': o['name'], 'partner': o['partner_name'],
             'date': fields.Date.to_string(o['date_order'].date()), 'amount': o['amount'],
             'type': 'OP' if o['is_op'] else 'OTC'}
            for o in sorted(orders, key=lambda o: o['date_order'])
            if o['invoice_status'] == 'to invoice'
        ]
        return {'rows': rows[:LIST_LIMIT], 'total': len(rows)}
