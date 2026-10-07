/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { formatCurrency } from "@web/core/currency";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    DashChart,
    INK,
    PRESETS,
    SERIES,
    barDataset,
    baseOptions,
    bucketRange,
    nextDay,
    periodLabel,
    presetRange,
    utcStartOfDay,
} from "@hospital_doctor_dashboard/dashboard/chart_utils";

const STATUS = {
    in_stock: { color: "#0ca30c", icon: "fa-check-circle" },
    low: { color: "#fab219", icon: "fa-exclamation-triangle" },
    out: { color: "#ec835a", icon: "fa-minus-circle" },
    negative: { color: "#d03b3b", icon: "fa-times-circle" },
};
const CRITICAL = "#d03b3b";
const AUTO_REFRESH_MS = 5 * 60 * 1000;

const LIST_TABS = [
    { key: "no_batch", label: "Medicines without batch", icon: "fa-tags" },
    { key: "expiring", label: "Expiring & expired batches", icon: "fa-hourglass-half" },
    { key: "negative", label: "Negative stock", icon: "fa-times-circle" },
    { key: "low", label: "Low & out of stock", icon: "fa-exclamation-triangle" },
];

export class InventoryDashboard extends Component {
    static template = "hospital_inventory_dashboard.Dashboard";
    static components = { DashChart };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this.presets = PRESETS;
        this.listTabs = LIST_TABS;
        this.statusStyle = STATUS;
        const [from, to] = presetRange("30d");
        this.state = useState({
            loading: true,
            error: false,
            preset: "30d",
            dateFrom: from.toISODate(),
            dateTo: to.toISODate(),
            warehouseId: "",
            scope: "medicine",
            options: { warehouses: [] },
            data: null,
            tables: {},
            listTab: "no_batch",
            expanded: null,
            fullscreen: false,
            lastUpdated: null,
        });
        this.charts = {};

        this.onFullscreenChange = () => {
            this.state.fullscreen = document.fullscreenElement === this.rootRef.el;
            clearInterval(this.refreshTimer);
            if (this.state.fullscreen) {
                // Wall-display mode: keep the numbers fresh.
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
            this.state.options = await this.orm.call("hospital.inventory.dashboard", "get_filter_options", []);
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

    // ------------------------------------------------------------------
    // Filters
    // ------------------------------------------------------------------
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

    async onWarehouseChange(ev) {
        this.state.warehouseId = ev.target.value;
        await this.load();
    }

    isWarehouseSelected(id) {
        return String(id) === String(this.state.warehouseId);
    }

    async setScope(scope) {
        if (this.state.scope !== scope) {
            this.state.scope = scope;
            await this.load();
        }
    }

    setListTab(key) {
        this.state.listTab = key;
    }

    toggleTable(key) {
        this.state.tables[key] = !this.state.tables[key];
    }

    // ------------------------------------------------------------------
    // Full screen
    // ------------------------------------------------------------------
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
        return { movement: "Stock movement", expiry: "Expiry profile", issued: "Most issued", value: "Stock value" }[
            this.state.expanded
        ];
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------
    async openProduct(row) {
        if (document.fullscreenElement) {
            await document.exitFullscreen();
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: row.template_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ---------------- Click-through to the records behind a bar
    canOpen(model) {
        return Boolean((this.state.options.drill || {})[model]);
    }

    async openList(name, model, domain) {
        if (!this.canOpen(model)) {
            return;
        }
        if (document.fullscreenElement) {
            await document.exitFullscreen();
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            domain,
            context: { create: false },
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    get periodText() {
        const p = this.state.data && this.state.data.period;
        return p ? periodLabel(p.date_from, p.date_to) : "";
    }

    /** Products in the dashboard scope (medicines or all stocked products). */
    get productScope() {
        return this.state.scope === "medicine" ? [["product_id.is_medicine", "=", true]] : [["product_id.is_storable", "=", true]];
    }

    movesDomain([from, to], extra) {
        return [
            ["state", "=", "done"],
            ["date", ">=", utcStartOfDay(from)],
            ["date", "<", utcStartOfDay(to)],
            ...this.productScope,
            ...extra,
        ];
    }

    openMovement(index, datasetIndex) {
        const data = this.state.data;
        const locs = data.location_ids;
        const range = bucketRange(data.movements.starts, index, this.state.dateFrom, this.state.dateTo);
        const received = datasetIndex === 0;
        const extra = received
            ? [["location_dest_id", "in", locs], ["location_id", "not in", locs]]
            : [["location_id", "in", locs], ["location_dest_id", "not in", locs]];
        return this.openList(`${received ? "Received" : "Issued"}: ${data.movements.labels[index]}`, "stock.move",
            this.movesDomain(range, extra));
    }

    openIssued(row) {
        const locs = this.state.data.location_ids;
        return this.openList(`Issued: ${row.name}`, "stock.move", this.movesDomain(
            [this.state.dateFrom, nextDay(this.state.dateTo)],
            [["product_id", "=", row.id], ["location_id", "in", locs], ["location_dest_id.usage", "=", "customer"]]));
    }

    openExpiry(bucket) {
        // Expiry dates are compared as UTC days, like the server buckets.
        const domain = [["location_id", "in", this.state.data.location_ids], ["quantity", ">", 0], ...this.productScope,
            ["lot_id", "!=", false]];
        if (bucket.exp_from) {
            domain.push(["lot_id.expiration_date", ">=", `${bucket.exp_from} 00:00:00`]);
        }
        if (bucket.exp_to) {
            domain.push(["lot_id.expiration_date", "<", `${nextDay(bucket.exp_to)} 00:00:00`]);
        }
        return this.openList(`Batches: ${bucket.label}`, "stock.quant", domain);
    }

    openValueGroup(row) {
        const scope = this.state.scope === "medicine" ? [["is_medicine", "=", true]] : [];
        return this.openList(`Products: ${row.name}`, "product.template",
            [["is_storable", "=", true], ...scope, ...row.domain]);
    }

    async openPendingDeliveries() {
        if (document.fullscreenElement) {
            await document.exitFullscreen();
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Waiting deliveries",
            res_model: "stock.picking",
            domain: [["id", "in", this.state.data.pending_picking_ids]],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    onTile(tile) {
        if (tile.list) {
            this.state.listTab = tile.list;
            const card = this.rootRef.el.querySelector(".o_hi_lists");
            if (card) {
                card.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        } else if (tile.key === "pending") {
            this.openPendingDeliveries();
        }
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call("hospital.inventory.dashboard", "get_dashboard_data", [
                this.state.dateFrom,
                this.state.dateTo,
                this.state.warehouseId ? Number(this.state.warehouseId) : false,
                this.state.scope,
            ]);
            this.charts = this.buildCharts(data);
            this.state.data = data;
            this.state.lastUpdated = luxon.DateTime.now().toFormat("HH:mm");
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

    qty(value) {
        return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    days(value) {
        if (value < 0) {
            return `Expired ${-value} d ago`;
        }
        return value === 0 ? "Expires today" : `${value} d left`;
    }

    get kpiTiles() {
        const k = this.state.data.kpis;
        return [
            { key: "value", label: "Stock value", value: this.money(k.stock_value, true), title: this.money(k.stock_value),
              hint: "On hand × cost" },
            { key: "products", label: "Products in stock", value: `${this.qty(k.in_stock + k.low)} / ${this.qty(k.products)}`,
              hint: "With positive stock" },
            { key: "no_batch", label: "Without batch", value: this.qty(k.no_batch), list: "no_batch",
              alert: k.no_batch > 0, hint: "Cannot be delivered from a batch" },
            { key: "expiring", label: "Expiring soon", value: this.qty(k.expiring), list: "expiring",
              hint: `${this.money(k.expiring_value)} at cost` },
            { key: "expired", label: "Expired, still in stock", value: this.qty(k.expired), list: "expiring",
              alert: k.expired > 0, hint: `${this.money(k.expired_value)} at cost` },
            { key: "negative", label: "Negative stock", value: this.qty(k.negative), list: "negative",
              alert: k.negative > 0, hint: "Sold without stock" },
            { key: "low", label: "Low / out of stock", value: `${this.qty(k.low)} / ${this.qty(k.out)}`, list: "low",
              hint: "Below minimum / zero" },
            { key: "pending", label: "Waiting deliveries", value: this.qty(k.pending_deliveries),
              alert: k.pending_deliveries > 0, hint: "Open the transfers" },
        ];
    }

    get movementLegend() {
        const k = this.state.data.kpis;
        return [
            { label: "Received", color: SERIES[0], value: this.qty(k.received_qty) },
            { label: "Issued", color: SERIES[1], value: this.qty(k.issued_qty) },
        ];
    }

    get bucketLabel() {
        return { day: "per day", week: "per week", month: "per month" }[this.state.data.period.bucket];
    }

    get hasMovement() {
        const k = this.state.data.kpis;
        return k.received_qty !== 0 || k.issued_qty !== 0;
    }

    get hasExpiry() {
        return this.state.data.expiry_chart.some((b) => b.lots > 0);
    }

    listCount(key) {
        return this.state.data.lists[key].total;
    }

    get currentList() {
        return this.state.data.lists[this.state.listTab];
    }

    buildCharts(data) {
        const money = (v) => this.money(v);
        const moneyShort = (v) => this.money(v, true);
        const qty = (v) => this.qty(v);
        const charts = {};

        charts.movement = () => ({
            type: "bar",
            data: {
                labels: data.movements.labels,
                datasets: [
                    barDataset("Received", data.movements.received, SERIES[0]),
                    barDataset("Issued", data.movements.issued, SERIES[1]),
                ],
            },
            options: baseOptions({
                format: qty,
                onBarClick: this.canOpen("stock.move") ? (i, ds) => this.openMovement(i, ds) : undefined,
            }),
        });

        charts.expiry = () => {
            const options = baseOptions({
                format: money,
                tickFormat: moneyShort,
                onBarClick: this.canOpen("stock.quant") ? (i) => this.openExpiry(data.expiry_chart[i]) : undefined,
                canClick: (i) => data.expiry_chart[i].lots > 0,
            });
            options.plugins.tooltip.callbacks.afterLabel = (ctx) => {
                const bucket = data.expiry_chart[ctx.dataIndex];
                return ` ${bucket.lots} batches · ${qty(bucket.qty)} units`;
            };
            return {
                type: "bar",
                data: {
                    labels: data.expiry_chart.map((b) => b.label),
                    datasets: [
                        barDataset("Stock value", data.expiry_chart.map((b) => b.value), data.expiry_chart.map(
                            (b) => (b.key === "expired" ? CRITICAL : SERIES[0])
                        ), { maxBarThickness: 48 }),
                    ],
                },
                options,
            };
        };

        charts.issued = () => ({
            type: "bar",
            data: {
                labels: data.issued_top.map((r) => r.name),
                datasets: [barDataset("Issued", data.issued_top.map((r) => r.qty), SERIES[0], { maxBarThickness: 20 })],
            },
            options: baseOptions({
                horizontal: true,
                format: qty,
                onBarClick: this.canOpen("stock.move") ? (i) => this.openIssued(data.issued_top[i]) : undefined,
            }),
        });

        charts.value = () => {
            const options = baseOptions({
                horizontal: true,
                format: money,
                tickFormat: moneyShort,
                onBarClick: this.canOpen("product.template") ? (i) => this.openValueGroup(data.value_groups[i]) : undefined,
                canClick: (i) => Boolean(data.value_groups[i] && data.value_groups[i].domain),
            });
            options.layout.padding.right = 90;
            options.plugins.hdBarEndLabels.format = moneyShort;
            return {
                type: "bar",
                data: {
                    labels: data.value_groups.map((r) => r.name),
                    datasets: [barDataset("Stock value", data.value_groups.map((r) => r.value), SERIES[0], { maxBarThickness: 20 })],
                },
                options,
            };
        };
        return charts;
    }

    chartHeight(rows) {
        return Math.max(180, rows * 30 + 40);
    }
}

registry.category("actions").add("hospital_inventory_dashboard", InventoryDashboard);
