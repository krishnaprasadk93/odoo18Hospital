/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DashboardBase } from "@hospital_doctor_dashboard/dashboard/dashboard_base";
import { SERIES, barDataset, baseOptions } from "@hospital_doctor_dashboard/dashboard/doctor_dashboard";

const ORDER_TYPES = [
    { key: "all", label: "All sales" },
    { key: "op", label: "OP pharmacy" },
    { key: "otc", label: "OTC" },
];

export class SalesDashboard extends DashboardBase {
    static template = "hospital_sales_dashboard.Dashboard";
    static model = "hospital.sales.dashboard";
    static chartTitles = {
        sales: "Sales",
        products: "Top products",
        customers: "Top customers",
        payments: "Payments received",
    };

    setup() {
        super.setup();
        this.orderTypes = ORDER_TYPES;
    }

    initialFilters() {
        return { orderType: "all", listTab: "unpaid" };
    }

    dataArgs() {
        return [this.state.dateFrom, this.state.dateTo, this.state.orderType];
    }

    get kpiTiles() {
        const k = this.state.data.kpis;
        return [
            { key: "sales", label: "Sales", value: this.money(k.sales), delta: this.delta(k.sales, k.sales_prev),
              hint: "Confirmed orders, incl. tax" },
            { key: "orders", label: "Orders", value: this.qty(k.orders), delta: this.delta(k.orders, k.orders_prev) },
            { key: "avg", label: "Average order", value: this.money(k.avg_order) },
            { key: "customers", label: "Customers", value: this.qty(k.customers), hint: `${this.qty(k.items)} items sold` },
            { key: "refunds", label: "Refunds", value: this.money(k.refunds), hint: "Posted credit notes" },
            { key: "to_invoice", label: "Orders to invoice", value: this.qty(k.to_invoice), alert: k.to_invoice > 0,
              hint: "Confirmed, not invoiced", onClick: () => this.showList("to_invoice") },
            { key: "unpaid", label: "Unpaid invoices", value: this.money(k.unpaid), alert: k.unpaid > 0,
              hint: "All open customer invoices", onClick: () => this.showList("unpaid") },
            { key: "overdue", label: "Overdue", value: this.money(k.overdue), alert: k.overdue > 0,
              hint: "Past due date", onClick: () => this.showList("unpaid") },
        ];
    }

    showList(key) {
        this.state.listTab = key;
        const card = this.rootRef.el.querySelector(".o_hd_lists");
        if (card) {
            card.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    get salesLegend() {
        const s = this.state.data.series;
        const sum = (arr) => arr.reduce((a, b) => a + b, 0);
        return [
            { label: "OP pharmacy", color: SERIES[0], value: this.money(sum(s.op)) },
            { label: "OTC", color: SERIES[1], value: this.money(sum(s.otc)) },
        ];
    }

    get hasSales() {
        return this.state.data.kpis.orders > 0;
    }

    get currentList() {
        return this.state.data.lists[this.state.listTab];
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
        charts.sales = () => {
            const datasets = [
                barDataset("OP pharmacy", data.series.op, SERIES[0]),
                barDataset("OTC", data.series.otc, SERIES[1]),
            ];
            for (const ds of datasets) {
                Object.assign(ds, {
                    borderRadius: (ctx) => {
                        const next = ctx.chart.data.datasets[ctx.datasetIndex + 1];
                        return next && ctx.chart.isDatasetVisible(ctx.datasetIndex + 1) && next.data[ctx.dataIndex]
                            ? 0
                            : { topLeft: 4, topRight: 4 };
                    },
                    borderSkipped: false,
                    borderWidth: { top: 2 },
                    borderColor: "#fcfcfb",
                });
            }
            return {
                type: "bar",
                data: { labels: data.series.labels, datasets },
                options: baseOptions({ stacked: true, format: money, tickFormat: moneyShort }),
            };
        };
        const ranked = (rows, key, label, isMoney) => () => {
            const options = baseOptions({
                horizontal: true,
                format: isMoney ? money : (v) => this.qty(v),
                tickFormat: isMoney ? moneyShort : undefined,
            });
            if (isMoney) {
                options.layout.padding.right = 90;
                options.plugins.hdBarEndLabels.format = moneyShort;
            }
            return {
                type: "bar",
                data: {
                    labels: rows.map((r) => r.name),
                    datasets: [barDataset(label, rows.map((r) => r[key]), SERIES[0], { maxBarThickness: 20 })],
                },
                options,
            };
        };
        charts.products = ranked(data.top_products, "amount", "Sales", true);
        charts.customers = ranked(data.top_customers, "amount", "Sales", true);
        charts.payments = ranked(data.payments, "amount", "Received", true);
        return charts;
    }
}

registry.category("actions").add("hospital_sales_dashboard", SalesDashboard);
