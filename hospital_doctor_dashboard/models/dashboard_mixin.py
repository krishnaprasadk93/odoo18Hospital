from datetime import datetime, time, timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

DOCTOR_GROUP = 'hospital_management.group_hospital_doctor'
MAX_RANGE_DAYS = 731


class HospitalDashboardMixin(models.AbstractModel):
    """ Shared rules for the clinic dashboards: doctors-only access, the
    hospitals (companies) a user may see, date ranges and time buckets. """
    _name = 'hospital.dashboard.mixin'
    _description = 'Clinic Dashboard Helpers'

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    def _check_doctor_access(self):
        if not self.env.user.has_group(DOCTOR_GROUP):
            raise AccessError(_("Only doctors can view the clinic dashboards."))

    def _allowed_company_ids(self, company_ids=None):
        """ Requested hospitals (companies), restricted to the user's own. """
        allowed = self.env.user.company_ids.ids
        if company_ids:
            ids = [int(c) for c in company_ids if int(c) in allowed]
            if ids:
                return ids
        return [c for c in self.env.companies.ids if c in allowed] or [self.env.company.id]

    def _drill_access(self, model_names):
        """ {model: bool}: whether the user may open these records (the
        dashboards read data with sudo, but click-through opens normal views). """
        access = {}
        for name in model_names:
            if name not in self.env:
                access[name] = False
                continue
            model = self.env[name]
            check = getattr(model, 'has_access', None)
            access[name] = bool(check('read')) if check else model.check_access_rights('read', raise_exception=False)
        return access

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------
    def _parse_range(self, date_from, date_to):
        d_from = fields.Date.to_date(date_from)
        d_to = fields.Date.to_date(date_to)
        if not d_from or not d_to or d_from > d_to:
            raise UserError(_("Please choose a valid date range."))
        if (d_to - d_from).days > MAX_RANGE_DAYS:
            raise UserError(_("Please choose a date range of at most two years."))
        return d_from, d_to

    @staticmethod
    def _previous_range(d_from, d_to):
        span = (d_to - d_from).days + 1
        prev_to = d_from - timedelta(days=1)
        return prev_to - timedelta(days=span - 1), prev_to

    def _user_tz(self):
        try:
            return pytz.timezone(self.env.user.tz or 'UTC')
        except pytz.UnknownTimeZoneError:
            return pytz.UTC

    def _utc_bounds(self, d_from, d_to):
        tz = self._user_tz()
        start = tz.localize(datetime.combine(d_from, time.min)).astimezone(pytz.UTC)
        end = tz.localize(datetime.combine(d_to + timedelta(days=1), time.min)).astimezone(pytz.UTC)
        return start.replace(tzinfo=None), end.replace(tzinfo=None)

    def _to_local_date(self, utc_dt):
        """ Convert in Python: PostgreSQL may not know legacy zone names (e.g. Asia/Calcutta). """
        return pytz.utc.localize(utc_dt).astimezone(self._user_tz()).date()

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
    def _bucket_starts(keys):
        """ ISO start date of each bucket (the client turns a clicked bar into a date range). """
        return [fields.Date.to_string(k) for k in keys]

    @staticmethod
    def _bucket_label(day, kind):
        if kind == 'month':
            return day.strftime('%b %Y')
        if kind == 'week':
            return 'Wk %s' % day.strftime('%d %b')
        return day.strftime('%d %b')

    @staticmethod
    def _top(rows, key, limit, other_label, name_key='name'):
        """ Keep the `limit` largest rows by `key`, folding the rest into one row. """
        ranked = sorted(rows, key=lambda r: -r[key])
        top = ranked[:limit]
        rest = sum(r[key] for r in ranked[limit:])
        if rest:
            top.append({name_key: other_label, key: rest})
        return top
