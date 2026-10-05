/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { formatCurrency } from "@web/core/currency";
import { useService } from "@web/core/utils/hooks";
import { DashChart, PRESETS, presetRange } from "./doctor_dashboard";

const AUTO_REFRESH_MS = 5 * 60 * 1000;

/**
 * Shared behaviour for the clinic dashboards: date range, refresh, browser
 * full screen (wall display, auto refresh), per-chart expand and table views.
 *
 * Subclasses set `static model` and implement `dataArgs()` and
 * `buildCharts(data)`; they may override `initialFilters()`.
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

    // ---------------- Formatting
    money(value, humanReadable = false) {
        const currencyId = this.state.data ? this.state.data.currency_id : this.state.options.currency_id;
        return formatCurrency(value || 0, currencyId, humanReadable ? { humanReadable: true } : {});
    }

    qty(value) {
        return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    delta(current, previous) {
        if (!previous) {
            return current ? { text: "New this period", dir: "flat" } : { text: "No change", dir: "flat" };
        }
        const pct = Math.round(((current - previous) / Math.abs(previous)) * 100);
        if (pct === 0) {
            return { text: "No change vs previous period", dir: "flat" };
        }
        return { text: `${Math.abs(pct)}% vs previous period`, dir: pct > 0 ? "up" : "down" };
    }

    get bucketLabel() {
        const bucket = this.state.data && this.state.data.period.bucket;
        return { day: "per day", week: "per week", month: "per month" }[bucket] || "";
    }

    chartHeight(rows) {
        return Math.max(180, rows * 30 + 40);
    }
}
