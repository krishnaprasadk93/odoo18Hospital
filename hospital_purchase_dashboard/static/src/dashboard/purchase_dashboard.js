/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DashboardBase } from "@hospital_doctor_dashboard/dashboard/dashboard_base";
import { SERIES, barDataset, baseOptions } from "@hospital_doctor_dashboard/dashboard/chart_utils";

const CRITICAL = "#d03b3b";
const PO = "purchase.order";
const MOVE = "account.move";

export class PurchaseDashboard extends DashboardBase {
    static template = "hospital_purchase_dashboard.Dashboard";
    static model = "hospital.purchase.dashboard";
    static chartTitles = {
        spend: "Purchases",
        vendors: "Top vendors",
        products: "Top purchased products",
        ageing: "Vendor bills to pay",
    };

    initialFilters() {
        return { listTab: "overdue" };
    }

    get kpiTiles() {
        const k = this.state.data.kpis;
        const money = (v) => this.money(v, true);
        const openPos = this.canOpen(PO) ? () => this.openPos("Purchase orders") : undefined;
        return [
            { key: "spend", label: "Purchases", ...this.moneyTile(k.spend), delta: this.delta(k.spend, k.spend_prev, money),
              hint: "Confirmed orders, incl. tax", onClick: openPos },
            { key: "orders", label: "Purchase orders", value: this.qty(k.orders), delta: this.delta(k.orders, k.orders_prev),
              hint: "Confirmed in this period", onClick: openPos },
            { key: "avg", label: "Average order", ...this.moneyTile(k.avg_order), hint: `${this.qty(k.vendors)} vendors` },
            { key: "rfqs", label: "Open RFQs", value: this.qty(k.rfqs), hint: "Draft / sent, not confirmed",
              onClick: this.canOpen(PO) ? () => this.openList("Open RFQs", PO, [["state", "in", ["draft", "sent", "to approve"]]]) : undefined },
            { key: "waiting", label: "Waiting receipt", value: this.qty(k.waiting_receipt), alert: k.waiting_receipt > 0,
              hint: "Confirmed, not fully received", onClick: () => this.showList("waiting") },
            { key: "bills", label: "Bills to pay", ...this.moneyTile(k.bills_due), hint: "All open vendor bills",
              onClick: () => this.showList("bills") },
            { key: "overdue", label: "Overdue bills", ...this.moneyTile(k.overdue), alert: k.overdue > 0,
              hint: `${this.qty(k.overdue_count)} bills past due`, onClick: () => this.showList("overdue") },
            { key: "vendors", label: "Vendors", value: this.qty(k.vendors), hint: "With confirmed orders" },
        ];
    }

    // ---------------- Click-through
    posDomain([from, to] = this.range, extra = []) {
        return [["state", "in", ["purchase", "done"]], ...this.datetimeDomain("date_approve", from, to), ...extra];
    }

    openPos(name, range = this.range, extra = []) {
        return this.openList(name, PO, this.posDomain(range, extra));
    }

    openBills(bucket) {
        const domain = [["move_type", "=", "in_invoice"], ["state", "=", "posted"],
            ["payment_state", "in", ["not_paid", "partial"]]];
        if (bucket.due_from) {
            domain.push(["invoice_date_due", ">=", bucket.due_from]);
        }
        if (bucket.due_to) {
            domain.push(["invoice_date_due", "<=", bucket.due_to]);
        }
        return this.openList(`Vendor bills: ${bucket.label}`, MOVE, domain);
    }

    showList(key) {
        this.state.listTab = key;
        const card = this.rootRef.el.querySelector(".o_hd_lists");
        if (card) {
            card.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    get listTabs() {
        const l = this.state.data.lists;
        return [
            { key: "overdue", label: "Overdue bills", icon: "fa-exclamation-circle", total: l.overdue.total },
            { key: "bills", label: "All bills to pay", icon: "fa-file-text-o", total: l.bills.total },
            { key: "waiting", label: "Waiting receipt", icon: "fa-truck", total: l.waiting.total },
        ];
    }

    get currentList() {
        return this.state.data.lists[this.state.listTab];
    }

    get hasSpend() {
        return this.state.data.kpis.orders > 0;
    }

    get hasBills() {
        return this.state.data.ageing.some((b) => b.count > 0);
    }

    overdueText(days) {
        if (days > 0) {
            return `${days} d overdue`;
        }
        return days === 0 ? "Due today" : `Due in ${-days} d`;
    }

    buildCharts(data) {
        const money = (v) => this.money(v);
        const moneyShort = (v) => this.money(v, true);
        const charts = {};
        charts.spend = () => ({
            type: "bar",
            data: { labels: data.series.labels, datasets: [barDataset("Purchases", data.series.spend, SERIES[0])] },
            options: baseOptions({
                format: money,
                tickFormat: moneyShort,
                onBarClick: this.canOpen(PO)
                    ? (i) => this.openPos(`Purchase orders: ${data.series.labels[i]}`, this.bucket(data.series.starts, i))
                    : undefined,
            }),
        });
        charts.ageing = () => {
            const options = baseOptions({
                format: money,
                tickFormat: moneyShort,
                onBarClick: this.canOpen(MOVE) ? (i) => this.openBills(data.ageing[i]) : undefined,
                canClick: (i) => data.ageing[i].count > 0,
            });
            options.plugins.tooltip.callbacks.afterLabel = (ctx) => ` ${data.ageing[ctx.dataIndex].count} bills`;
            return {
                type: "bar",
                data: {
                    labels: data.ageing.map((b) => b.label),
                    datasets: [barDataset("Amount due", data.ageing.map((b) => b.amount),
                        data.ageing.map((b) => (b.key.startsWith("over") ? CRITICAL : SERIES[0])), { maxBarThickness: 48 })],
                },
                options,
            };
        };
        const ranked = (rows, onRow) => () => {
            const options = baseOptions({
                horizontal: true,
                format: money,
                tickFormat: moneyShort,
                onBarClick: this.canOpen(PO) ? (i) => onRow(rows[i]) : undefined,
                canClick: (i) => Boolean(rows[i] && rows[i].id),
            });
            options.layout.padding.right = 90;
            options.plugins.hdBarEndLabels.format = moneyShort;
            return {
                type: "bar",
                data: {
                    labels: rows.map((r) => r.name),
                    datasets: [barDataset("Purchases", rows.map((r) => r.amount), SERIES[0], { maxBarThickness: 20 })],
                },
                options,
            };
        };
        charts.vendors = ranked(data.top_vendors, (r) => this.openPos(`Purchase orders: ${r.name}`, this.range,
            [["partner_id", "=", r.id]]));
        charts.products = ranked(data.top_products, (r) => this.openPos(`Purchase orders with ${r.name}`, this.range,
            [["order_line.product_id", "=", r.id]]));
        return charts;
    }
}

registry.category("actions").add("hospital_purchase_dashboard", PurchaseDashboard);
