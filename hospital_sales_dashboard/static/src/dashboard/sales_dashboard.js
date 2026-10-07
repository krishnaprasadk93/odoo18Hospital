/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DashboardBase } from "@hospital_doctor_dashboard/dashboard/dashboard_base";
import { SERIES, barDataset, baseOptions } from "@hospital_doctor_dashboard/dashboard/chart_utils";

const ORDER = "sale.order";
const PAYMENT = "account.payment";
const MOVE = "account.move";

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
        const money = (v) => this.money(v, true);
        const openOrders = this.canOpen(ORDER) ? () => this.openOrders("Sales orders") : undefined;
        return [
            { key: "sales", label: "Sales", ...this.moneyTile(k.sales), delta: this.delta(k.sales, k.sales_prev, money),
              hint: "Confirmed orders, incl. tax", onClick: openOrders },
            { key: "orders", label: "Orders", value: this.qty(k.orders), delta: this.delta(k.orders, k.orders_prev),
              hint: "Confirmed in this period", onClick: openOrders },
            { key: "avg", label: "Average order", ...this.moneyTile(k.avg_order) },
            { key: "customers", label: "Customers", value: this.qty(k.customers), hint: `${this.qty(k.items)} items sold` },
            { key: "refunds", label: "Refunds", ...this.moneyTile(k.refunds), hint: "Posted credit notes",
              onClick: this.canOpen(MOVE) ? () => this.openRefunds() : undefined },
            { key: "to_invoice", label: "Orders to invoice", value: this.qty(k.to_invoice), alert: k.to_invoice > 0,
              hint: "Confirmed, not invoiced", onClick: () => this.showList("to_invoice") },
            { key: "unpaid", label: "Unpaid invoices", ...this.moneyTile(k.unpaid), alert: k.unpaid > 0,
              hint: "All open customer invoices", onClick: () => this.showList("unpaid") },
            { key: "overdue", label: "Overdue", ...this.moneyTile(k.overdue), alert: k.overdue > 0,
              hint: "Past due date", onClick: () => this.showList("unpaid") },
        ];
    }

    // ---------------- Click-through
    /** Confirmed orders of the period (and order type), optionally narrowed. */
    ordersDomain([from, to] = this.range, type = this.state.orderType, extra = []) {
        const domain = [["state", "in", ["sale", "done"]], ...this.datetimeDomain("date_order", from, to)];
        if (type === "op") {
            domain.push(["op_ticket_id", "!=", false]);
        } else if (type === "otc") {
            domain.push(["op_ticket_id", "=", false]);
        }
        return [...domain, ...extra];
    }

    openOrders(name, range = this.range, type = this.state.orderType, extra = []) {
        return this.openList(name, ORDER, this.ordersDomain(range, type, extra));
    }

    openRefunds() {
        return this.openList("Refunds", MOVE, [
            ["move_type", "=", "out_refund"], ["state", "=", "posted"], ...this.dateDomain("invoice_date", ...this.range),
        ]);
    }

    openPayments(row) {
        return this.openList(`Payments: ${row.name}`, PAYMENT, [
            ["journal_id", "=", row.id], ["payment_type", "=", "inbound"], ["partner_type", "=", "customer"],
            ["state", "not in", ["draft", "canceled", "rejected"]], ...this.dateDomain("date", ...this.range),
        ]);
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
                options: baseOptions({
                    stacked: true,
                    format: money,
                    tickFormat: moneyShort,
                    // Clicked segment: OP pharmacy (0) or OTC (1) orders of that period.
                    onBarClick: this.canOpen(ORDER)
                        ? (i, ds) => this.openOrders(`${ds === 0 ? "OP pharmacy" : "OTC"} orders: ${data.series.labels[i]}`,
                              this.bucket(data.series.starts, i), ds === 0 ? "op" : "otc")
                        : undefined,
                }),
            };
        };
        const ranked = (rows, key, label, isMoney, onRow, model = ORDER) => () => {
            const options = baseOptions({
                horizontal: true,
                format: isMoney ? money : (v) => this.qty(v),
                tickFormat: isMoney ? moneyShort : undefined,
                onBarClick: this.canOpen(model) ? (i) => onRow(rows[i]) : undefined,
                canClick: (i) => Boolean(rows[i] && rows[i].id),
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
        charts.products = ranked(data.top_products, "amount", "Sales", true,
            (r) => this.openOrders(`Orders with ${r.name}`, this.range, this.state.orderType, [["order_line.product_id", "=", r.id]]));
        charts.customers = ranked(data.top_customers, "amount", "Sales", true,
            (r) => this.openOrders(`Orders: ${r.name}`, this.range, this.state.orderType, [["partner_id", "=", r.id]]));
        charts.payments = ranked(data.payments, "amount", "Received", true, (r) => this.openPayments(r), PAYMENT);
        return charts;
    }
}

registry.category("actions").add("hospital_sales_dashboard", SalesDashboard);
