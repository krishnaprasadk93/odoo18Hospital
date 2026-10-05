/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DashboardBase } from "@hospital_doctor_dashboard/dashboard/dashboard_base";
import { SERIES, barDataset, baseOptions } from "@hospital_doctor_dashboard/dashboard/doctor_dashboard";

const CRITICAL = "#d03b3b";

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
        return [
            { key: "spend", label: "Purchases", value: this.money(k.spend), delta: this.delta(k.spend, k.spend_prev),
              hint: "Confirmed orders, incl. tax" },
            { key: "orders", label: "Purchase orders", value: this.qty(k.orders), delta: this.delta(k.orders, k.orders_prev) },
            { key: "avg", label: "Average order", value: this.money(k.avg_order), hint: `${this.qty(k.vendors)} vendors` },
            { key: "rfqs", label: "Open RFQs", value: this.qty(k.rfqs), hint: "Draft / sent, not confirmed" },
            { key: "waiting", label: "Waiting receipt", value: this.qty(k.waiting_receipt), alert: k.waiting_receipt > 0,
              hint: "Confirmed, not fully received", onClick: () => this.showList("waiting") },
            { key: "bills", label: "Bills to pay", value: this.money(k.bills_due), hint: "All open vendor bills",
              onClick: () => this.showList("bills") },
            { key: "overdue", label: "Overdue bills", value: this.money(k.overdue), alert: k.overdue > 0,
              hint: `${this.qty(k.overdue_count)} bills past due`, onClick: () => this.showList("overdue") },
            { key: "vendors", label: "Vendors", value: this.qty(k.vendors), hint: "With confirmed orders" },
        ];
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
            options: baseOptions({ format: money, tickFormat: moneyShort }),
        });
        charts.ageing = () => {
            const options = baseOptions({ format: money, tickFormat: moneyShort });
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
        const ranked = (rows) => () => {
            const options = baseOptions({ horizontal: true, format: money, tickFormat: moneyShort });
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
        charts.vendors = ranked(data.top_vendors);
        charts.products = ranked(data.top_products);
        return charts;
    }
}

registry.category("actions").add("hospital_purchase_dashboard", PurchaseDashboard);
