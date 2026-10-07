/** @odoo-module **/

import { Component, useEffect, useRef } from "@odoo/owl";
import { user } from "@web/core/user";

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

// ---------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------

/** "6 Sep – 5 Oct 2026", "28 Dec 2025 – 3 Jan 2026" or "6 Sep 2026". */
export function periodLabel(from, to) {
    const a = DateTime.fromISO(from);
    const b = DateTime.fromISO(to);
    if (!a.isValid || !b.isValid) {
        return `${from} – ${to}`;
    }
    if (a.hasSame(b, "day")) {
        return b.toFormat("d LLL yyyy");
    }
    return `${a.toFormat(a.hasSame(b, "year") ? "d LLL" : "d LLL yyyy")} – ${b.toFormat("d LLL yyyy")}`;
}

/** UTC "yyyy-MM-dd HH:mm:ss" of the start of `isoDate` in the user's time zone (for datetime domains). */
export function utcStartOfDay(isoDate) {
    let day = DateTime.fromISO(isoDate, { zone: user.tz || "local" });
    if (!day.isValid) {
        day = DateTime.fromISO(isoDate);
    }
    return day.startOf("day").toUTC().toFormat("yyyy-MM-dd HH:mm:ss");
}

/** ISO date of the day after `isoDate`. */
export function nextDay(isoDate) {
    return DateTime.fromISO(isoDate).plus({ days: 1 }).toISODate();
}

/**
 * Date range [from, toExclusive) of bucket `index` of a time series whose
 * buckets start at `starts`, clipped to the dashboard range [dateFrom, dateTo].
 */
export function bucketRange(starts, index, dateFrom, dateTo) {
    const from = starts[index] < dateFrom ? dateFrom : starts[index];
    const end = index + 1 < starts.length ? starts[index + 1] : nextDay(dateTo);
    return [from, end];
}

// ---------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------

/** Rounded 4px data-end only on the top-most visible segment of a stack. */
export function stackTopRadius(ctx) {
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

/**
 * Shared chart options. `onBarClick(index, datasetIndex)` makes the bars
 * clickable (pointer cursor on hover) to open the matching records; it may
 * return false for bars that open nothing (e.g. "Other").
 */
export function baseOptions({
    horizontal = false,
    stacked = false,
    format = (v) => String(v),
    tickFormat,
    onBarClick,
    canClick = () => true,
}) {
    const valueAxis = horizontal ? "x" : "y";
    const categoryAxis = horizontal ? "y" : "x";
    const hit = (chart, evt) => {
        const els = chart.getElementsAtEventForMode(evt, "nearest", { intersect: true, axis: categoryAxis }, false);
        return els.length && canClick(els[0].index, els[0].datasetIndex) ? els[0] : null;
    };
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        indexAxis: horizontal ? "y" : "x",
        layout: { padding: { right: horizontal ? 48 : 4, top: 4 } },
        interaction: { mode: "index", intersect: false, axis: categoryAxis },
        onClick: onBarClick
            ? (evt, _elements, chart) => {
                  const el = hit(chart, evt);
                  if (el) {
                      onBarClick(el.index, el.datasetIndex);
                  }
              }
            : undefined,
        onHover: onBarClick
            ? (evt, _elements, chart) => {
                  chart.canvas.style.cursor = hit(chart, evt) ? "pointer" : "default";
              }
            : undefined,
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
                // Long time ranges: show a label every few bars instead of crowding them.
                ticks: horizontal
                    ? { color: INK.muted, autoSkip: true, maxRotation: 0 }
                    : { color: INK.muted, autoSkip: true, autoSkipPadding: 14, maxRotation: 0, maxTicksLimit: 12 },
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
