/** @odoo-module **/

import { Component, markRaw, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { formatCurrency } from "@web/core/currency";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

// Chart roles (reference data-viz palette, validated: blue / orange / aqua).
export const INK = {
    primary: "#0b0b0b",
    secondary: "#52514e",
    muted: "#898781",
    grid: "#e1e0d9",
    baseline: "#c3c2b7",
    surface: "#fcfcfb",
    border: "rgba(11,11,11,0.10)",
};
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a"];
export const NEUTRAL = "#c3c2b7";

export const PRESETS = [
    { key: "today", label: "Today" },
    { key: "7d", label: "Last 7 days" },
    { key: "30d", label: "Last 30 days" },
    { key: "month", label: "This month" },
    { key: "last_month", label: "Last month" },
    { key: "90d", label: "Last 90 days" },
    { key: "year", label: "This year" },
];

export function presetRange(key) {
    const today = DateTime.now().startOf("day");
    switch (key) {
        case "today":
            return [today, today];
        case "7d":
            return [today.minus({ days: 6 }), today];
        case "30d":
            return [today.minus({ days: 29 }), today];
        case "month":
            return [today.startOf("month"), today];
        case "last_month": {
            const start = today.minus({ months: 1 }).startOf("month");
            return [start, start.endOf("month").startOf("day")];
        }
        case "90d":
            return [today.minus({ days: 89 }), today];
        case "year":
            return [today.startOf("year"), today];
    }
    return [today.minus({ days: 29 }), today];
}

/** Rounded 4px data-end only on the top-most visible segment of a stack. */
function stackTopRadius(ctx) {
    const { chart, dataIndex, datasetIndex } = ctx;
    for (let i = datasetIndex + 1; i < chart.data.datasets.length; i++) {
        if (chart.isDatasetVisible(i) && chart.data.datasets[i].data[dataIndex]) {
            return 0;
        }
    }
    return { topLeft: 4, topRight: 4 };
}

/** Value labels at the end of horizontal bars (ranked lists of <= 10 rows). */
const barEndLabels = {
    id: "hdBarEndLabels",
    afterDatasetsDraw(chart, _args, opts) {
        if (!opts || !opts.enabled) {
            return;
        }
        const { ctx } = chart;
        ctx.save();
        ctx.font = "12px system-ui, -apple-system, 'Segoe UI', sans-serif";
        ctx.fillStyle = INK.secondary;
        ctx.textBaseline = "middle";
        const meta = chart.getDatasetMeta(0);
        meta.data.forEach((bar, i) => {
            const value = chart.data.datasets[0].data[i];
            ctx.fillText(opts.format ? opts.format(value) : String(value), bar.x + 6, bar.y);
        });
        ctx.restore();
    },
};

export function baseOptions({ horizontal = false, stacked = false, format = (v) => String(v), tickFormat }) {
    const valueAxis = horizontal ? "x" : "y";
    const categoryAxis = horizontal ? "y" : "x";
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        indexAxis: horizontal ? "y" : "x",
        layout: { padding: { right: horizontal ? 48 : 4, top: 4 } },
        interaction: { mode: "index", intersect: false, axis: categoryAxis },
        plugins: {
            legend: { display: false },
            hdBarEndLabels: { enabled: horizontal, format },
            tooltip: {
                backgroundColor: "#ffffff",
                titleColor: INK.primary,
                bodyColor: INK.secondary,
                borderColor: INK.border,
                borderWidth: 1,
                padding: 10,
                boxPadding: 4,
                usePointStyle: true,
                callbacks: {
                    label: (ctx) => {
                        const value = ctx.parsed[valueAxis];
                        const label = ctx.dataset.label ? `${ctx.dataset.label}: ` : "";
                        return ` ${label}${format(value)}`;
                    },
                    footer: stacked
                        ? (items) => `Total: ${format(items.reduce((sum, i) => sum + i.parsed[valueAxis], 0))}`
                        : undefined,
                },
                footerColor: INK.primary,
            },
        },
        scales: {
            [valueAxis]: {
                beginAtZero: true,
                stacked,
                grid: { color: INK.grid, drawTicks: false },
                border: { display: false },
                ticks: {
                    color: INK.muted,
                    padding: 6,
                    maxTicksLimit: 5,
                    precision: 0,
                    callback: tickFormat || undefined,
                },
            },
            [categoryAxis]: {
                stacked,
                grid: { display: false },
                border: { color: INK.baseline },
                ticks: { color: INK.muted, autoSkip: true, maxRotation: 0 },
            },
        },
    };
}

export function barDataset(label, data, color, extra = {}) {
    return {
        label,
        data,
        backgroundColor: color,
        hoverBackgroundColor: color,
        borderRadius: 4,
        borderSkipped: "start",
        maxBarThickness: 28,
        categoryPercentage: 0.75,
        barPercentage: 0.9,
        ...extra,
    };
}

export class DashChart extends Component {
    static template = "hospital_doctor_dashboard.DashChart";
    static props = {
        config: [Object, Function],
        label: String,
        height: { type: Number, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        useEffect(
            (config) => {
                // A factory gives each chart instance its own config (Chart.js mutates it).
                const resolved = typeof config === "function" ? config() : config;
                const chart = new Chart(this.canvasRef.el, {
                    ...resolved,
                    plugins: [barEndLabels],
                });
                return () => chart.destroy();
            },
            () => [this.props.config]
        );
    }
}

export class DoctorDashboard extends Component {
    static template = "hospital_doctor_dashboard.Dashboard";
    static components = { DashChart };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.presets = PRESETS;
        const [from, to] = presetRange("30d");
        this.state = useState({
            loading: true,
            error: false,
            preset: "30d",
            dateFrom: from.toISODate(),
            dateTo: to.toISODate(),
            companyIds: [],
            doctorId: "",
            options: { companies: [], doctors: [] },
            data: null,
            tables: {},
        });
        this.charts = {};
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            this.state.options = await this.orm.call("hospital.doctor.dashboard", "get_filter_options", []);
            this.state.companyIds = [...this.state.options.default_company_ids];
            await this.load();
        });
    }

    // ------------------------------------------------------------------
    // Filters
    // ------------------------------------------------------------------
    get visibleDoctors() {
        const ids = new Set(this.state.companyIds);
        return this.state.options.doctors.filter((d) => ids.has(d.company_id));
    }

    async onPreset(key) {
        const [from, to] = presetRange(key);
        this.state.preset = key;
        this.state.dateFrom = from.toISODate();
        this.state.dateTo = to.toISODate();
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

    async toggleCompany(companyId) {
        const ids = new Set(this.state.companyIds);
        if (ids.has(companyId)) {
            if (ids.size === 1) {
                return; // keep at least one hospital selected
            }
            ids.delete(companyId);
        } else {
            ids.add(companyId);
        }
        this.state.companyIds = [...ids];
        if (this.state.doctorId && !this.visibleDoctors.some((d) => d.id === Number(this.state.doctorId))) {
            this.state.doctorId = "";
        }
        await this.load();
    }

    isDoctorSelected(doctorId) {
        return String(doctorId) === String(this.state.doctorId);
    }

    async onDoctorChange(ev) {
        this.state.doctorId = ev.target.value;
        await this.load();
    }

    toggleTable(key) {
        this.state.tables[key] = !this.state.tables[key];
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call("hospital.doctor.dashboard", "get_dashboard_data", [
                this.state.dateFrom,
                this.state.dateTo,
                this.state.companyIds,
                this.state.doctorId ? Number(this.state.doctorId) : false,
            ]);
            this.charts = this.buildCharts(data);
            this.state.data = data;
        } catch (e) {
            this.state.error = (e.data && e.data.message) || e.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    money(value, humanReadable = false) {
        const currencyId = this.state.data ? this.state.data.currency_id : this.state.options.currency_id;
        return formatCurrency(value || 0, currencyId, humanReadable ? { humanReadable: true } : {});
    }

    count(value) {
        return Number(value || 0).toLocaleString();
    }

    percent(value) {
        return `${Math.round((value || 0) * 100)}%`;
    }

    delta(current, previous) {
        if (!previous) {
            return current ? { text: "New this period", dir: "flat" } : { text: "No change", dir: "flat" };
        }
        const pct = Math.round(((current - previous) / Math.abs(previous)) * 100);
        if (pct === 0) {
            return { text: "No change vs previous period", dir: "flat" };
        }
        return {
            text: `${Math.abs(pct)}% vs previous period`,
            dir: pct > 0 ? "up" : "down",
        };
    }

    get kpiTiles() {
        const k = this.state.data.kpis;
        return [
            { key: "visits", label: "Visits", value: this.count(k.visits), delta: this.delta(k.visits, k.visits_prev),
              hint: `${this.count(k.cancelled)} cancelled` },
            { key: "patients", label: "Patients seen", value: this.count(k.patients),
              delta: this.delta(k.patients, k.patients_prev) },
            { key: "new", label: "New patients", value: this.count(k.new_patients),
              delta: this.delta(k.new_patients, k.new_patients_prev), hint: "First visit in this period" },
            { key: "revenue", label: "Revenue", value: this.money(k.revenue_total),
              delta: this.delta(k.revenue_total, k.revenue_total_prev), hint: "Posted invoices, incl. tax" },
            { key: "avg", label: "Revenue per visit", value: this.money(k.avg_revenue_per_visit) },
            { key: "rx", label: "Visits with prescription", value: this.percent(k.prescription_rate) },
        ];
    }

    get procedureTiles() {
        const k = this.state.data.kpis;
        return [
            { key: "procedures", label: "Procedures prescribed", value: this.count(k.procedures),
              delta: this.delta(k.procedures, k.procedures_prev) },
            { key: "proc_value", label: "Procedure value", value: this.money(k.procedure_value),
              delta: this.delta(k.procedure_value, k.procedure_value_prev), hint: "Qty × price on the visits" },
            { key: "proc_rate", label: "Visits with a procedure", value: this.percent(k.procedure_rate) },
        ];
    }

    get hasProcedures() {
        return this.state.data && this.state.data.kpis.procedures > 0;
    }

    get revenueLegend() {
        const k = this.state.data.kpis;
        const items = [
            { label: "Consultation", color: SERIES[0], value: this.money(k.revenue_consultation) },
            { label: "Pharmacy", color: SERIES[1], value: this.money(k.revenue_pharmacy) },
        ];
        if (k.revenue_other) {
            items.push({ label: "Other", color: SERIES[2], value: this.money(k.revenue_other) });
        }
        return items;
    }

    get hasVisits() {
        return this.state.data && this.state.data.kpis.visits > 0;
    }

    get hasRevenue() {
        return this.state.data && this.state.data.kpis.revenue_total !== 0;
    }

    mixRows(items) {
        const total = items.reduce((s, i) => s + i.count, 0);
        return items
            .map((item, idx) => ({
                ...item,
                pct: total ? item.count / total : 0,
                color: item.label === "Not set" ? NEUTRAL : SERIES[idx % SERIES.length],
            }))
            .filter((i) => i.count > 0);
    }

    get bucketLabel() {
        return { day: "per day", week: "per week", month: "per month" }[this.state.data.period.bucket];
    }

    buildCharts(data) {
        const money = (v) => this.money(v);
        const moneyShort = (v) => this.money(v, true);
        const count = (v) => this.count(v);
        const charts = {};

        charts.visits = {
            type: "bar",
            data: {
                labels: data.visits_series.labels,
                datasets: [barDataset("Visits", data.visits_series.values, SERIES[0])],
            },
            options: baseOptions({ format: count }),
        };

        const revenueDatasets = [
            barDataset("Consultation", data.revenue_series.consultation, SERIES[0]),
            barDataset("Pharmacy", data.revenue_series.pharmacy, SERIES[1]),
        ];
        if (data.revenue_series.other.some((v) => v)) {
            revenueDatasets.push(barDataset("Other", data.revenue_series.other, SERIES[2]));
        }
        for (const ds of revenueDatasets) {
            // 2px surface gap between stacked segments, rounded end on the top segment only.
            Object.assign(ds, {
                borderRadius: stackTopRadius,
                borderSkipped: false,
                borderWidth: { top: 2 },
                borderColor: INK.surface,
            });
        }
        charts.revenue = {
            type: "bar",
            data: { labels: data.revenue_series.labels, datasets: revenueDatasets },
            options: baseOptions({ stacked: true, format: money, tickFormat: moneyShort }),
        };

        charts.hours = {
            type: "bar",
            data: {
                labels: data.hours_series.labels,
                datasets: [barDataset("Visits", data.hours_series.values, SERIES[0])],
            },
            options: baseOptions({ format: count }),
        };

        charts.doctors = {
            type: "bar",
            data: {
                labels: data.doctors.map((d) => d.name),
                datasets: [barDataset("Visits", data.doctors.map((d) => d.visits), SERIES[0], { maxBarThickness: 20 })],
            },
            options: baseOptions({ horizontal: true, format: count }),
        };

        charts.medicines = {
            type: "bar",
            data: {
                labels: data.medicines.map((m) => m.name),
                datasets: [barDataset("Times prescribed", data.medicines.map((m) => m.count), SERIES[0], { maxBarThickness: 20 })],
            },
            options: baseOptions({ horizontal: true, format: count }),
        };

        // ---------------- Procedures
        const proc = data.procedures;
        charts.procTop = {
            type: "bar",
            data: {
                labels: proc.top.map((p) => p.name),
                datasets: [barDataset("Times prescribed", proc.top.map((p) => p.count), SERIES[0], { maxBarThickness: 20 })],
            },
            options: baseOptions({ horizontal: true, format: count }),
        };
        const valueOptions = baseOptions({ horizontal: true, format: money, tickFormat: moneyShort });
        valueOptions.layout.padding.right = 90;
        valueOptions.plugins.hdBarEndLabels.format = moneyShort;
        charts.procValue = {
            type: "bar",
            data: {
                labels: proc.by_value.map((p) => p.name),
                datasets: [barDataset("Value", proc.by_value.map((p) => p.value), SERIES[0], { maxBarThickness: 20 })],
            },
            options: valueOptions,
        };
        charts.procSeries = {
            type: "bar",
            data: {
                labels: proc.series.labels,
                datasets: [barDataset("Procedures", proc.series.values, SERIES[0])],
            },
            options: baseOptions({ format: count }),
        };
        charts.procDoctors = {
            type: "bar",
            data: {
                labels: proc.doctors.map((d) => d.name),
                datasets: [barDataset("Procedures", proc.doctors.map((d) => d.count), SERIES[0], { maxBarThickness: 20 })],
            },
            options: baseOptions({ horizontal: true, format: count }),
        };

        // Chart.js mutates its config: keep it out of OWL's reactivity.
        for (const key in charts) {
            charts[key] = markRaw(charts[key]);
        }
        return charts;
    }

    chartHeight(rows) {
        return Math.max(160, rows * 30 + 40);
    }
}

registry.category("actions").add("hospital_doctor_dashboard", DoctorDashboard);
