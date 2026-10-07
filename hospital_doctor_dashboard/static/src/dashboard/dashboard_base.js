/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { formatCurrency } from "@web/core/currency";
import { useService } from "@web/core/utils/hooks";
import { DashChart, PRESETS, bucketRange, nextDay, periodLabel, presetRange, utcStartOfDay } from "./chart_utils";

const AUTO_REFRESH_MS = 5 * 60 * 1000;

/**
 * Shared behaviour for the clinic dashboards: date range, refresh, browser
 * full screen (wall display, auto refresh), per-chart expand and table views.
 *
 * Subclasses set `static model` and implement `dataArgs()` and
 * `buildCharts(data)`; they may override `initialFilters()` and
 * `onOptionsLoaded(options)`.
 */
export class DashboardBase extends Component {
    static components = { DashChart };
    static props = ["*"];
    static model = "";
    static chartTitles = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this.presets = PRESETS;
        const [from, to] = presetRange("30d");
        this.state = useState({
            loading: true,
            error: false,
            preset: "30d",
            dateFrom: from.toISODate(),
            dateTo: to.toISODate(),
            options: {},
            data: null,
            tables: {},
            expanded: null,
            fullscreen: false,
            lastUpdated: null,
            ...this.initialFilters(),
        });
        this.charts = {};

        this.onFullscreenChange = () => {
            this.state.fullscreen = document.fullscreenElement === this.rootRef.el;
            clearInterval(this.refreshTimer);
            if (this.state.fullscreen) {
                this.refreshTimer = setInterval(() => this.load(), AUTO_REFRESH_MS);
            }
        };
        this.onKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.expanded) {
                this.state.expanded = null;
            }
        };
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            this.state.options = await this.orm.call(this.constructor.model, "get_filter_options", []);
            this.onOptionsLoaded(this.state.options);
            await this.load();
        });
        onMounted(() => {
            document.addEventListener("fullscreenchange", this.onFullscreenChange);
            document.addEventListener("keydown", this.onKeydown);
        });
        onWillUnmount(() => {
            document.removeEventListener("fullscreenchange", this.onFullscreenChange);
            document.removeEventListener("keydown", this.onKeydown);
            clearInterval(this.refreshTimer);
            if (document.fullscreenElement === this.rootRef.el) {
                document.exitFullscreen();
            }
        });
    }

    initialFilters() {
        return {};
    }

    onOptionsLoaded() {}

    dataArgs() {
        return [this.state.dateFrom, this.state.dateTo];
    }

    buildCharts() {
        return {};
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call(this.constructor.model, "get_dashboard_data", this.dataArgs());
            this.charts = this.buildCharts(data);
            this.state.data = data;
            this.state.lastUpdated = luxon.DateTime.now().toFormat("HH:mm");
        } catch (e) {
            this.state.error = (e.data && e.data.message) || e.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    // ---------------- Filters
    async onPreset(key) {
        const [from, to] = presetRange(key);
        Object.assign(this.state, { preset: key, dateFrom: from.toISODate(), dateTo: to.toISODate() });
        await this.load();
    }

    async onDateChange(field, ev) {
        if (!ev.target.value) {
            return;
        }
        this.state[field] = ev.target.value;
        this.state.preset = "custom";
        if (this.state.dateFrom > this.state.dateTo) {
            if (field === "dateFrom") {
                this.state.dateTo = this.state.dateFrom;
            } else {
                this.state.dateFrom = this.state.dateTo;
            }
        }
        await this.load();
    }

    async setFilter(key, value) {
        if (this.state[key] !== value) {
            this.state[key] = value;
            await this.load();
        }
    }

    toggleTable(key) {
        this.state.tables[key] = !this.state.tables[key];
    }

    // ---------------- Full screen & expand
    async toggleFullscreen() {
        if (document.fullscreenElement) {
            await document.exitFullscreen();
        } else if (this.rootRef.el.requestFullscreen) {
            await this.rootRef.el.requestFullscreen();
        }
    }

    expand(key) {
        this.state.expanded = key;
    }

    closeExpanded() {
        this.state.expanded = null;
    }

    get expandedHeight() {
        return Math.max(320, window.innerHeight - 170);
    }

    get expandedTitle() {
        return this.constructor.chartTitles[this.state.expanded] || "";
    }

    async openAction(action) {
        if (document.fullscreenElement) {
            await document.exitFullscreen();
        }
        await this.action.doAction(action);
    }

    openRecord(model, id) {
        return this.openAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ---------------- Click-through to the records behind a tile or bar

    /** Whether the user may open `model` (the server reports read access per model). */
    canOpen(model) {
        const drill = this.state.options.drill || {};
        return Boolean(drill[model]);
    }

    /** Open a list (and form) of `model` filtered by `domain`, if the user may read it. */
    openList(name, model, domain, context = {}) {
        if (!this.canOpen(model)) {
            return;
        }
        return this.openAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            domain,
            context: { create: false, ...context },
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    /** Domain on a datetime field for the days [from, toExclusive) in the user's time zone. */
    datetimeDomain(field, from, toExclusive) {
        return [[field, ">=", utcStartOfDay(from)], [field, "<", utcStartOfDay(toExclusive)]];
    }

    /** Domain on a date field for the days [from, toExclusive). */
    dateDomain(field, from, toExclusive) {
        return [[field, ">=", from], [field, "<", toExclusive]];
    }

    /** [from, toExclusive) of the whole dashboard range. */
    get range() {
        return [this.state.dateFrom, nextDay(this.state.dateTo)];
    }

    /** [from, toExclusive) of bucket `index` of a time series (`starts` from the server). */
    bucket(starts, index) {
        return bucketRange(starts, index, this.state.dateFrom, this.state.dateTo);
    }

    // ---------------- Formatting
    money(value, humanReadable = false) {
        const currencyId = this.state.data ? this.state.data.currency_id : this.state.options.currency_id;
        return formatCurrency(value || 0, currencyId, humanReadable ? { humanReadable: true } : {});
    }

    /** Short money for tiles ("₹ 90.97k"), with the exact amount as `title` (hover). */
    moneyTile(value) {
        return { value: this.money(value, true), title: this.money(value) };
    }

    qty(value) {
        return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    count(value) {
        return Number(value || 0).toLocaleString();
    }

    percent(value) {
        return `${Math.round((value || 0) * 100)}%`;
    }

    /**
     * Comparison with the previous period. Very large swings (from a tiny
     * previous period) read as noise in %, so show the previous value instead.
     */
    delta(current, previous, format = (v) => this.qty(v)) {
        if (!previous) {
            return current ? { text: "New this period", dir: "flat" } : { text: "No change", dir: "flat" };
        }
        const pct = Math.round(((current - previous) / Math.abs(previous)) * 100);
        if (pct === 0) {
            return { text: "No change vs previous period", dir: "flat" };
        }
        const dir = pct > 0 ? "up" : "down";
        if (Math.abs(pct) >= 200) {
            return { text: `${dir === "up" ? "Up" : "Down"} from ${format(previous)} last period`, dir };
        }
        return { text: `${Math.abs(pct)}% vs previous period`, dir };
    }

    /** "6 Sep – 5 Oct 2026" for the loaded period. */
    get periodText() {
        const p = this.state.data && this.state.data.period;
        return p ? periodLabel(p.date_from, p.date_to) : "";
    }

    get previousPeriodText() {
        const p = this.state.data && this.state.data.period;
        return p && p.prev_from ? periodLabel(p.prev_from, p.prev_to) : "";
    }

    get bucketLabel() {
        const bucket = this.state.data && this.state.data.period.bucket;
        return { day: "per day", week: "per week", month: "per month" }[bucket] || "";
    }

    chartHeight(rows) {
        return Math.max(180, rows * 30 + 40);
    }
}
