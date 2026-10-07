/** @odoo-module **/

import { registry } from "@web/core/registry";
import { INK, NEUTRAL, SERIES, barDataset, baseOptions, stackTopRadius } from "./chart_utils";
import { DashboardBase } from "./dashboard_base";

// Chart helpers used to live here: keep exporting them for other modules.
export * from "./chart_utils";

const VISIT = "hospital.op.ticket";
const PATIENT = "hospital.patient";
const MOVE = "account.move";

export class DoctorDashboard extends DashboardBase {
    static template = "hospital_doctor_dashboard.Dashboard";
    static model = "hospital.doctor.dashboard";
    static chartTitles = {
        visits: "Visits",
        revenue: "Revenue",
        doctors: "Visits by doctor",
        medicines: "Most prescribed medicines",
        hours: "Busiest hours",
        procTop: "Most prescribed procedures",
        procValue: "Procedure value",
        procSeries: "Procedures over time",
        procDoctors: "Procedures by doctor",
    };

    initialFilters() {
        return { companyIds: [], doctorId: "" };
    }

    onOptionsLoaded(options) {
        this.state.companyIds = [...(options.default_company_ids || [])];
    }

    dataArgs() {
        return [
            this.state.dateFrom,
            this.state.dateTo,
            this.state.companyIds,
            this.state.doctorId ? Number(this.state.doctorId) : false,
        ];
    }

    // ------------------------------------------------------------------
    // Filters
    // ------------------------------------------------------------------
    get visibleDoctors() {
        const ids = new Set(this.state.companyIds);
        return (this.state.options.doctors || []).filter((d) => ids.has(d.company_id));
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

    // ------------------------------------------------------------------
    // Click-through
    // ------------------------------------------------------------------
    /** Visits of the dashboard filters (hospitals, doctor) in [from, to). */
    visitsDomain([from, to] = this.range, extra = [], includeCancelled = false) {
        const domain = this.datetimeDomain("appointment_date", from, to);
        if (!includeCancelled) {
            domain.push(["state", "!=", "cancelled"]);
        }
        if (this.state.companyIds.length) {
            domain.push(["doctor_id.company_id", "in", this.state.companyIds]);
        }
        if (this.state.doctorId) {
            domain.push(["doctor_id", "=", Number(this.state.doctorId)]);
        }
        return [...domain, ...extra];
    }

    openVisits(name, extra = [], range = this.range, includeCancelled = false) {
        return this.openList(name, VISIT, this.visitsDomain(range, extra, includeCancelled));
    }

    openInvoices(name, [from, to] = this.range) {
        const domain = [
            ["move_type", "in", ["out_invoice", "out_refund"]],
            ["state", "=", "posted"],
            ...this.dateDomain("invoice_date", from, to),
        ];
        if (this.state.companyIds.length) {
            domain.push(["company_id", "in", this.state.companyIds]);
        }
        return this.openList(name, MOVE, domain);
    }

    /** onClick for a tile, only when the user may open the records. */
    clickIf(model, fn) {
        return this.canOpen(model) ? fn : undefined;
    }

    openStatus(status) {
        if (this.canOpen(VISIT)) {
            this.openVisits(`Visits: ${status.label}`, [["state", "=", status.key]], this.range, true);
        }
    }

    // ------------------------------------------------------------------
    // Tiles
    // ------------------------------------------------------------------
    get kpiTiles() {
        const k = this.state.data.kpis;
        const money = (v) => this.money(v, true);
        return [
            { key: "visits", label: "Visits", value: this.count(k.visits), delta: this.delta(k.visits, k.visits_prev),
              hint: `${this.count(k.cancelled)} cancelled`, onClick: this.clickIf(VISIT, () => this.openVisits("Visits")) },
            { key: "patients", label: "Patients seen", value: this.count(k.patients),
              delta: this.delta(k.patients, k.patients_prev), hint: "Distinct patients",
              onClick: this.clickIf(PATIENT, () => this.openList("Patients seen", PATIENT,
                  [["visit_ids", "any", this.visitsDomain()]])) },
            { key: "new", label: "New patients", value: this.count(k.new_patients),
              delta: this.delta(k.new_patients, k.new_patients_prev), hint: "First visit in this period" },
            { key: "revenue", label: "Revenue", ...this.moneyTile(k.revenue_total),
              delta: this.delta(k.revenue_total, k.revenue_total_prev, money), hint: "Posted invoices, incl. tax",
              onClick: this.clickIf(MOVE, () => this.openInvoices("Invoices")) },
            { key: "avg", label: "Revenue per visit", ...this.moneyTile(k.avg_revenue_per_visit) },
            { key: "rx", label: "Visits with prescription", value: this.percent(k.prescription_rate),
              hint: "Share of visits",
              onClick: this.clickIf(VISIT, () => this.openVisits("Visits with prescription",
                  [["prescription_ids", "!=", false]])) },
        ];
    }

    get procedureTiles() {
        const k = this.state.data.kpis;
        const money = (v) => this.money(v, true);
        const openProcVisits = this.clickIf(VISIT, () => this.openVisits("Visits with a procedure",
            [["procedure_line_ids", "!=", false]]));
        return [
            { key: "procedures", label: "Procedures prescribed", value: this.count(k.procedures),
              delta: this.delta(k.procedures, k.procedures_prev), hint: "On the visits above", onClick: openProcVisits },
            { key: "proc_value", label: "Procedure value", ...this.moneyTile(k.procedure_value),
              delta: this.delta(k.procedure_value, k.procedure_value_prev, money), hint: "Qty × price on the visits",
              onClick: openProcVisits },
            { key: "proc_rate", label: "Visits with a procedure", value: this.percent(k.procedure_rate),
              hint: "Share of visits", onClick: openProcVisits },
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

    // ------------------------------------------------------------------
    // Charts (factories: the expanded view renders its own copy)
    // ------------------------------------------------------------------
    buildCharts(data) {
        const money = (v) => this.money(v);
        const moneyShort = (v) => this.money(v, true);
        const count = (v) => this.count(v);
        const canVisit = this.canOpen(VISIT);
        const charts = {};

        const ranked = (rows, key, label, extra, isMoney = false) => () => {
            const options = baseOptions({
                horizontal: true,
                format: isMoney ? money : count,
                tickFormat: isMoney ? moneyShort : undefined,
                onBarClick: canVisit ? (i) => this.openVisits(`Visits: ${rows[i].name}`, extra(rows[i])) : undefined,
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

        const visitStarts = data.visits_series.starts;
        charts.visits = () => ({
            type: "bar",
            data: {
                labels: data.visits_series.labels,
                datasets: [barDataset("Visits", data.visits_series.values, SERIES[0])],
            },
            options: baseOptions({
                format: count,
                onBarClick: canVisit
                    ? (i) => this.openVisits(`Visits: ${data.visits_series.labels[i]}`, [], this.bucket(visitStarts, i))
                    : undefined,
            }),
        });

        charts.revenue = () => {
            const datasets = [
                barDataset("Consultation", data.revenue_series.consultation, SERIES[0]),
                barDataset("Pharmacy", data.revenue_series.pharmacy, SERIES[1]),
            ];
            if (data.revenue_series.other.some((v) => v)) {
                datasets.push(barDataset("Other", data.revenue_series.other, SERIES[2]));
            }
            for (const ds of datasets) {
                // 2px surface gap between stacked segments, rounded end on the top segment only.
                Object.assign(ds, {
                    borderRadius: stackTopRadius,
                    borderSkipped: false,
                    borderWidth: { top: 2 },
                    borderColor: INK.surface,
                });
            }
            return {
                type: "bar",
                data: { labels: data.revenue_series.labels, datasets },
                options: baseOptions({
                    stacked: true,
                    format: money,
                    tickFormat: moneyShort,
                    onBarClick: this.canOpen(MOVE)
                        ? (i) => this.openInvoices(`Invoices: ${data.revenue_series.labels[i]}`,
                              this.bucket(data.revenue_series.starts, i))
                        : undefined,
                }),
            };
        };

        charts.hours = () => ({
            type: "bar",
            data: {
                labels: data.hours_series.labels,
                datasets: [barDataset("Visits", data.hours_series.values, SERIES[0])],
            },
            options: baseOptions({ format: count }),
        });

        charts.doctors = ranked(data.doctors, "visits", "Visits", (r) => [["doctor_id", "=", r.id]]);
        charts.medicines = ranked(data.medicines, "count", "Times prescribed",
            (r) => [["prescription_ids.medicine_id", "=", r.id]]);

        // ---------------- Procedures
        const proc = data.procedures;
        const procExtra = (r) => [["procedure_line_ids.product_id", "=", r.id]];
        charts.procTop = ranked(proc.top, "count", "Times prescribed", procExtra);
        charts.procValue = ranked(proc.by_value, "value", "Value", procExtra, true);
        charts.procSeries = () => ({
            type: "bar",
            data: { labels: proc.series.labels, datasets: [barDataset("Procedures", proc.series.values, SERIES[0])] },
            options: baseOptions({
                format: count,
                onBarClick: canVisit
                    ? (i) => this.openVisits(`Visits with a procedure: ${proc.series.labels[i]}`,
                          [["procedure_line_ids", "!=", false]], this.bucket(proc.series.starts, i))
                    : undefined,
            }),
        });
        charts.procDoctors = ranked(proc.doctors, "count", "Procedures",
            (r) => [["doctor_id", "=", r.id], ["procedure_line_ids", "!=", false]]);
        return charts;
    }
}

registry.category("actions").add("hospital_doctor_dashboard", DoctorDashboard);
