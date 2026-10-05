from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

ACCESS_GROUPS = (
    'hospital_management.group_hospital_pharmacist',
    'stock.group_stock_manager',
)
MAX_RANGE_DAYS = 731
LIST_LIMIT = 100
TOP_ISSUED = 10
PENDING_STATES = ('confirmed', 'waiting', 'partially_available', 'assigned')
EXPIRY_BUCKETS = [
    ('expired', 'Expired', None, 0),
    ('30', '≤ 30 days', 0, 30),
    ('60', '31–60 days', 30, 60),
    ('90', '61–90 days', 60, 90),
    ('180', '91–180 days', 90, 180),
    ('later', '> 180 days', 180, None),
]


class HospitalInventoryDashboard(models.AbstractModel):
    _name = 'hospital.inventory.dashboard'
    _description = 'Inventory Dashboard (Pharmacy)'

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    def _check_access(self):
        if not any(self.env.user.has_group(g) for g in ACCESS_GROUPS):
            raise AccessError(_("Only pharmacists and inventory administrators can view the inventory dashboard."))

    def _company_ids(self):
        allowed = self.env.user.company_ids.ids
        return [c for c in self.env.companies.ids if c in allowed] or [self.env.company.id]

    # ------------------------------------------------------------------
    # Public RPC
    # ------------------------------------------------------------------
    @api.model
    def get_filter_options(self):
        self._check_access()
        warehouses = self.env['stock.warehouse'].sudo().search(
            [('company_id', 'in', self._company_ids())], order='sequence, name')
        return {
            'warehouses': [{'id': w.id, 'name': w.name} for w in warehouses],
            'currency_id': self.env.company.currency_id.id,
        }

    @api.model
    def get_dashboard_data(self, date_from, date_to, warehouse_id=False, scope='medicine'):
        self._check_access()
        d_from = fields.Date.to_date(date_from)
        d_to = fields.Date.to_date(date_to)
        if not d_from or not d_to or d_from > d_to:
            raise UserError(_("Please choose a valid date range."))
        if (d_to - d_from).days > MAX_RANGE_DAYS:
            raise UserError(_("Please choose a date range of at most two years."))

        company_ids = self._company_ids()
        location_ids = self._internal_location_ids(warehouse_id, company_ids)
        products = self._scope_products(scope, company_ids)
        product_ids = products.ids
        currency = self.env['res.company'].browse(company_ids[0]).currency_id
        if not product_ids or not location_ids:
            return self._empty(d_from, d_to, currency)

        cost = {p.id: p.standard_price for p in products}
        stock = self._stock_by_product(product_ids, location_ids)
        lots = self._lot_stock(product_ids, location_ids)
        pending = self._pending_out(product_ids, location_ids)
        batch_counts = self._batch_counts(product_ids, company_ids)

        statuses, low_rows, out_rows = self._stock_status(products, stock, pending)
        no_batch_rows = self._no_batch_rows(products, stock, lots, batch_counts, pending)
        expiry_chart, expiry_rows, expiry_kpis = self._expiry(products, lots, cost)
        negative_rows = self._negative_rows(products, location_ids)
        movements, issued_top = self._movements(d_from, d_to, product_ids, location_ids, products)
        value_groups = self._value_groups(products, stock, cost, scope)

        stock_value = sum(stock.get(pid, 0.0) * cost[pid] for pid in product_ids if stock.get(pid, 0.0) > 0)
        pending_pickings = self._pending_pickings(product_ids, location_ids)

        kpis = {
            'stock_value': stock_value,
            'products': len(product_ids),
            'in_stock': statuses['in_stock'],
            'low': statuses['low'],
            'out': statuses['out'],
            'negative': statuses['negative'],
            'no_batch': len(no_batch_rows),
            'expiring': expiry_kpis['expiring'],
            'expiring_value': expiry_kpis['expiring_value'],
            'expired': expiry_kpis['expired'],
            'expired_value': expiry_kpis['expired_value'],
            'pending_deliveries': len(pending_pickings),
            'issued_qty': sum(movements['issued']),
            'received_qty': sum(movements['received']),
        }
        return {
            'period': {
                'date_from': fields.Date.to_string(d_from),
                'date_to': fields.Date.to_string(d_to),
                'bucket': movements['bucket'],
            },
            'currency_id': currency.id,
            'kpis': kpis,
            'status': [
                {'key': 'in_stock', 'label': _('In stock'), 'count': statuses['in_stock']},
                {'key': 'low', 'label': _('Low stock'), 'count': statuses['low']},
                {'key': 'out', 'label': _('Out of stock'), 'count': statuses['out']},
                {'key': 'negative', 'label': _('Negative stock'), 'count': statuses['negative']},
            ],
            'movements': movements,
            'issued_top': issued_top,
            'expiry_chart': expiry_chart,
            'value_groups': value_groups,
            'pending_picking_ids': pending_pickings,
            'lists': {
                'no_batch': self._cap(no_batch_rows),
                'expiring': self._cap(expiry_rows),
                'negative': self._cap(negative_rows),
                'low': self._cap(out_rows + low_rows),
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _cap(rows):
        return {'rows': rows[:LIST_LIMIT], 'total': len(rows)}

    def _empty(self, d_from, d_to, currency):
        empty_list = {'rows': [], 'total': 0}
        return {
            'period': {'date_from': fields.Date.to_string(d_from), 'date_to': fields.Date.to_string(d_to), 'bucket': 'day'},
            'currency_id': currency.id,
            'kpis': dict.fromkeys([
                'stock_value', 'products', 'in_stock', 'low', 'out', 'negative', 'no_batch', 'expiring',
                'expiring_value', 'expired', 'expired_value', 'pending_deliveries', 'issued_qty', 'received_qty'], 0),
            'status': [],
            'movements': {'labels': [], 'received': [], 'issued': [], 'bucket': 'day'},
            'issued_top': [],
            'expiry_chart': [],
            'value_groups': [],
            'pending_picking_ids': [],
            'lists': {k: empty_list for k in ('no_batch', 'expiring', 'negative', 'low')},
        }

    def _internal_location_ids(self, warehouse_id, company_ids):
        Location = self.env['stock.location'].sudo()
        domain = [('usage', '=', 'internal'), ('company_id', 'in', company_ids)]
        if warehouse_id:
            warehouse = self.env['stock.warehouse'].sudo().browse(int(warehouse_id))
            if warehouse.company_id.id not in company_ids:
                raise AccessError(_("You cannot access this warehouse."))
            domain.append(('id', 'child_of', warehouse.view_location_id.id))
        return Location.search(domain).ids

    def _scope_products(self, scope, company_ids):
        domain = [
            ('is_storable', '=', True),
            '|', ('company_id', '=', False), ('company_id', 'in', company_ids),
        ]
        if scope == 'medicine':
            domain.append(('product_tmpl_id.is_medicine', '=', True))
        return self.env['product.product'].sudo().with_company(company_ids[0]).search(domain)

    def _stock_by_product(self, product_ids, location_ids):
        self.env.cr.execute("""
            SELECT product_id, SUM(quantity)
              FROM stock_quant
             WHERE product_id = ANY(%s) AND location_id = ANY(%s)
          GROUP BY product_id
        """, [product_ids, location_ids])
        return dict(self.env.cr.fetchall())

    def _lot_stock(self, product_ids, location_ids):
        """ Per product and lot (None = no lot): quantity and expiry date. """
        self.env.cr.execute("""
            SELECT q.product_id, q.lot_id, SUM(q.quantity), MAX(l.name), MAX(l.expiration_date)
              FROM stock_quant q
         LEFT JOIN stock_lot l ON l.id = q.lot_id
             WHERE q.product_id = ANY(%s) AND q.location_id = ANY(%s)
          GROUP BY q.product_id, q.lot_id
        """, [product_ids, location_ids])
        lots = defaultdict(list)
        for product_id, lot_id, qty, name, expiry in self.env.cr.fetchall():
            lots[product_id].append({'lot_id': lot_id, 'qty': qty, 'name': name, 'expiry': expiry})
        return lots

    def _pending_out(self, product_ids, location_ids):
        """ Quantity waiting to leave stock (not yet delivered), per product. """
        self.env.cr.execute("""
            SELECT m.product_id, SUM(m.product_qty)
              FROM stock_move m
              JOIN stock_location dest ON dest.id = m.location_dest_id
             WHERE m.product_id = ANY(%s) AND m.location_id = ANY(%s)
               AND m.state = ANY(%s) AND dest.usage != 'internal'
          GROUP BY m.product_id
        """, [product_ids, location_ids, list(PENDING_STATES)])
        return dict(self.env.cr.fetchall())

    def _pending_pickings(self, product_ids, location_ids):
        self.env.cr.execute("""
            SELECT DISTINCT p.id
              FROM stock_picking p
              JOIN stock_picking_type t ON t.id = p.picking_type_id
              JOIN stock_move m ON m.picking_id = p.id
             WHERE t.code = 'outgoing' AND p.state IN ('confirmed', 'waiting')
               AND m.product_id = ANY(%s) AND m.location_id = ANY(%s)
        """, [product_ids, location_ids])
        return [r[0] for r in self.env.cr.fetchall()]

    def _batch_counts(self, product_ids, company_ids):
        self.env.cr.execute("""
            SELECT product_id, COUNT(*)
              FROM stock_lot
             WHERE product_id = ANY(%s) AND (company_id IS NULL OR company_id = ANY(%s))
          GROUP BY product_id
        """, [product_ids, company_ids])
        return dict(self.env.cr.fetchall())

    @staticmethod
    def _product_row(product, **extra):
        tmpl = product.product_tmpl_id
        row = {
            'product_id': product.id,
            'template_id': tmpl.id,
            'name': product.display_name,
            'type': dict(tmpl._fields['medicine_type'].selection).get(tmpl.medicine_type, '') if 'medicine_type' in tmpl._fields else '',
            'uom': product.uom_id.name,
        }
        row.update(extra)
        return row

    def _stock_status(self, products, stock, pending):
        counts = dict.fromkeys(('in_stock', 'low', 'out', 'negative'), 0)
        low_rows, out_rows = [], []
        for product in products:
            qty = stock.get(product.id, 0.0)
            rounding = product.uom_id.rounding
            minimum = product.minimum_qty if 'minimum_qty' in product._fields else 0.0
            if qty < -rounding / 2:
                counts['negative'] += 1
            elif abs(qty) < rounding / 2:
                counts['out'] += 1
                out_rows.append(self._product_row(
                    product, status='out', on_hand=0.0, minimum=minimum,
                    shortage=max(minimum, 0.0), pending=pending.get(product.id, 0.0)))
            elif minimum > 0 and qty < minimum:
                counts['low'] += 1
                low_rows.append(self._product_row(
                    product, status='low', on_hand=qty, minimum=minimum,
                    shortage=minimum - qty, pending=pending.get(product.id, 0.0)))
            else:
                counts['in_stock'] += 1
        low_rows.sort(key=lambda r: r['on_hand'] / r['minimum'] if r['minimum'] else 1)
        out_rows.sort(key=lambda r: -r['pending'])
        return counts, low_rows, out_rows

    def _no_batch_rows(self, products, stock, lots, batch_counts, pending):
        """ Batch-tracked medicines that cannot be delivered from a batch: no batch
        exists at all, or part of the on-hand stock is not assigned to a batch. """
        rows = []
        for product in products.filtered(lambda p: p.tracking != 'none'):
            batches = batch_counts.get(product.id, 0)
            untracked = sum(l['qty'] for l in lots.get(product.id, []) if not l['lot_id'])
            rounding = product.uom_id.rounding
            if batches and abs(untracked) < rounding / 2:
                continue
            issue = _('No batch created') if not batches else _('Stock without batch')
            rows.append(self._product_row(
                product, issue=issue, batches=batches, on_hand=stock.get(product.id, 0.0),
                untracked=untracked, pending=pending.get(product.id, 0.0)))
        rows.sort(key=lambda r: (-r['pending'], r['batches'], r['name']))
        return rows

    def _expiry(self, products, lots, cost):
        today = fields.Date.context_today(self)
        by_id = {p.id: p for p in products}
        buckets = {key: {'qty': 0.0, 'value': 0.0, 'lots': 0} for key, *_rest in EXPIRY_BUCKETS}
        rows = []
        kpis = {'expiring': 0, 'expiring_value': 0.0, 'expired': 0, 'expired_value': 0.0}
        for product_id, items in lots.items():
            product = by_id[product_id]
            alert_days = getattr(product, 'expiry_alert_days', 0) or 90
            for lot in items:
                if not lot['lot_id'] or not lot['expiry'] or lot['qty'] <= 0:
                    continue
                days = (lot['expiry'].date() - today).days
                value = lot['qty'] * cost.get(product_id, 0.0)
                key = self._expiry_bucket(days)
                buckets[key]['qty'] += lot['qty']
                buckets[key]['value'] += value
                buckets[key]['lots'] += 1
                if days < 0:
                    kpis['expired'] += 1
                    kpis['expired_value'] += value
                elif days <= alert_days:
                    kpis['expiring'] += 1
                    kpis['expiring_value'] += value
                if days <= alert_days:
                    rows.append(self._product_row(
                        product, batch=lot['name'], expiry=fields.Date.to_string(lot['expiry'].date()),
                        days=days, qty=lot['qty'], value=value))
        rows.sort(key=lambda r: r['days'])
        chart = [{'key': key, 'label': label, **buckets[key]} for key, label, *_rest in EXPIRY_BUCKETS]
        return chart, rows, kpis

    @staticmethod
    def _expiry_bucket(days):
        if days < 0:
            return 'expired'
        for key, _label, low, high in EXPIRY_BUCKETS[1:]:
            if high is None or days <= high:
                return key
        return 'later'

    def _negative_rows(self, products, location_ids):
        self.env.cr.execute("""
            SELECT q.product_id, l.name, loc.complete_name, SUM(q.quantity)
              FROM stock_quant q
              JOIN stock_location loc ON loc.id = q.location_id
         LEFT JOIN stock_lot l ON l.id = q.lot_id
             WHERE q.product_id = ANY(%s) AND q.location_id = ANY(%s)
          GROUP BY q.product_id, l.name, loc.complete_name
            HAVING SUM(q.quantity) < 0
          ORDER BY SUM(q.quantity)
        """, [products.ids, location_ids])
        by_id = {p.id: p for p in products}
        return [
            self._product_row(by_id[pid], batch=lot or '', location=loc, qty=qty)
            for pid, lot, loc, qty in self.env.cr.fetchall()
        ]

    # ---------------- Movements over time
    @staticmethod
    def _bucket_kind(d_from, d_to):
        span = (d_to - d_from).days + 1
        return 'day' if span <= 62 else 'week' if span <= 182 else 'month'

    @staticmethod
    def _bucket_start(day, kind):
        if kind == 'week':
            return day - timedelta(days=day.weekday())
        if kind == 'month':
            return day.replace(day=1)
        return day

    def _movements(self, d_from, d_to, product_ids, location_ids, products):
        try:
            tz = pytz.timezone(self.env.user.tz or 'UTC')
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        start = tz.localize(datetime.combine(d_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = tz.localize(datetime.combine(d_to + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        self.env.cr.execute("""
            SELECT m.product_id, m.product_qty,
                   m.date AS utc_date,
                   (m.location_dest_id = ANY(%(locs)s) AND NOT m.location_id = ANY(%(locs)s)) AS is_in,
                   (m.location_id = ANY(%(locs)s) AND NOT m.location_dest_id = ANY(%(locs)s)) AS is_out,
                   dest.usage AS dest_usage
              FROM stock_move m
              JOIN stock_location dest ON dest.id = m.location_dest_id
             WHERE m.state = 'done' AND m.product_id = ANY(%(products)s)
               AND m.date >= %(start)s AND m.date < %(end)s
               AND (m.location_id = ANY(%(locs)s) OR m.location_dest_id = ANY(%(locs)s))
        """, {'locs': location_ids, 'products': product_ids,
              'start': start, 'end': end})
        kind = self._bucket_kind(d_from, d_to)
        keys, day = [], self._bucket_start(d_from, kind)
        while day <= d_to:
            keys.append(day)
            if kind == 'day':
                day += timedelta(days=1)
            elif kind == 'week':
                day += timedelta(days=7)
            else:
                day = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
        received, issued = defaultdict(float), defaultdict(float)
        issued_by_product = defaultdict(float)
        for product_id, qty, utc_date, is_in, is_out, dest_usage in self.env.cr.fetchall():
            # Convert in Python: PostgreSQL may not know legacy zone names (e.g. Asia/Calcutta).
            day = pytz.utc.localize(utc_date).astimezone(tz).date()
            bucket = self._bucket_start(day, kind)
            if is_in:
                received[bucket] += qty
            elif is_out:
                issued[bucket] += qty
                if dest_usage == 'customer':
                    issued_by_product[product_id] += qty
        if kind == 'month':
            labels = [k.strftime('%b %Y') for k in keys]
        elif kind == 'week':
            labels = ['Wk %s' % k.strftime('%d %b') for k in keys]
        else:
            labels = [k.strftime('%d %b') for k in keys]
        by_id = {p.id: p for p in products}
        top = sorted(issued_by_product.items(), key=lambda kv: -kv[1])[:TOP_ISSUED]
        issued_top = [{'name': by_id[pid].display_name, 'qty': qty} for pid, qty in top]
        return {
            'labels': labels,
            'received': [round(received[k], 2) for k in keys],
            'issued': [round(issued[k], 2) for k in keys],
            'bucket': kind,
        }, issued_top

    def _value_groups(self, products, stock, cost, scope):
        groups = defaultdict(float)
        for product in products:
            qty = stock.get(product.id, 0.0)
            if qty <= 0:
                continue
            tmpl = product.product_tmpl_id
            if scope == 'medicine' and 'medicine_type' in tmpl._fields:
                label = dict(tmpl._fields['medicine_type'].selection).get(tmpl.medicine_type) or _('Not set')
            else:
                label = product.categ_id.display_name or _('Not set')
            groups[label] += qty * cost.get(product.id, 0.0)
        ranked = sorted(((k, v) for k, v in groups.items() if v), key=lambda kv: -kv[1])
        result = [{'name': name, 'value': round(value, 2)} for name, value in ranked[:8]]
        rest = sum(v for _n, v in ranked[8:])
        if rest:
            result.append({'name': _('Other'), 'value': round(rest, 2)})
        return result
