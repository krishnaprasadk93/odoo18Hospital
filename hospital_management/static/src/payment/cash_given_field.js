/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";

/**
 * "Cash given by customer" in the payment popups: the usual number input plus
 * one-tap amounts (exact, then the next round notes above the cash due), and
 * Enter to pay (presses the popup's primary button).
 */
export class CashGivenField extends Component {
    static template = "hospital_management.CashGivenField";
    static components = { FloatField };
    static props = {
        ...FloatField.props,
        cashField: { type: String },
    };

    get floatProps() {
        const { cashField, ...props } = this.props;
        return props;
    }

    get cashDue() {
        return this.props.record.data[this.props.cashField] || 0;
    }

    get quickAmounts() {
        const due = this.cashDue;
        if (due <= 0) {
            return [];
        }
        const amounts = [{ value: due, label: _t("Exact") }];
        for (const step of [10, 50, 100, 500, 2000]) {
            const value = Math.ceil(due / step) * step;
            if (value > due && !amounts.some((a) => a.value === value)) {
                amounts.push({ value, label: String(value) });
            }
        }
        return amounts.slice(0, 5);
    }

    setAmount(value) {
        this.props.record.update({ [this.props.name]: value });
    }

    onKeydown(ev) {
        if (ev.key !== "Enter" || ev.target.tagName !== "INPUT") {
            return;
        }
        ev.preventDefault();
        const payButton = ev.target.closest(".modal-content")?.querySelector(".modal-footer .btn-primary");
        // Leaving the input commits the typed amount before the button runs.
        ev.target.blur();
        if (payButton) {
            setTimeout(() => payButton.click());
        }
    }
}

export const cashGivenField = {
    ...floatField,
    component: CashGivenField,
    extractProps: (fieldInfo, dynamicInfo) => ({
        ...floatField.extractProps(fieldInfo, dynamicInfo),
        cashField: fieldInfo.options.cash_field || "cash_amount",
    }),
};

registry.category("fields").add("hc_cash_given", cashGivenField);
