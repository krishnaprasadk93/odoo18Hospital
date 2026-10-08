/** @odoo-module **/

import { useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";

const FRACTIONS = { 0.25: "¼", 0.5: "½", 0.75: "¾" };

/** 0 -> "0", 1.5 -> "1.5" (or "1½" for tablets), 0.3 -> "0.3" */
export function formatDose(value, useFractions) {
    value = Number(value) || 0;
    if (useFractions) {
        const whole = Math.trunc(value);
        const part = Math.round((value - whole) * 100) / 100;
        if (FRACTIONS[part]) {
            return (whole ? String(whole) : "") + FRACTIONS[part];
        }
    }
    return String(Math.round(value * 100) / 100);
}

/**
 * Dose entry for tablets and laptops: [−] value [+] with one-tap quick doses.
 * The doctor can always type any value (0.3, 1.2, 7.5...); the step and the
 * chips come from the medicine (or its type preset) via the line's
 * dose_step / dose_quick_values / dose_fraction fields.
 */
export class DoseField extends FloatField {
    static template = "hospital_management.DoseField";

    setup() {
        super.setup();
        this.doseWrap = useRef("doseWrap");
        this.state.popTop = 0;
        this.state.popLeft = 0;
    }

    onFocusIn() {
        // Place the floating bar under the cell (fixed, so the list's
        // scroll container never clips it) and keep it on screen.
        const el = this.doseWrap.el;
        if (el) {
            const rect = el.getBoundingClientRect();
            const approxWidth = 56 * (this.quickDoses.length + 2);
            this.state.popTop = Math.round(rect.bottom + 6);
            this.state.popLeft = Math.round(Math.max(8, Math.min(rect.left, window.innerWidth - approxWidth - 8)));
        }
        super.onFocusIn();
    }

    get popStyle() {
        return `top: ${this.state.popTop}px; left: ${this.state.popLeft}px;`;
    }

    get step() {
        return Number(this.props.record.data.dose_step) || 0.5;
    }

    get useFractions() {
        return Boolean(this.props.record.data.dose_fraction);
    }

    get quickDoses() {
        return String(this.props.record.data.dose_quick_values || "")
            .split(",")
            .map((v) => parseFloat(v))
            .filter((v) => v > 0);
    }

    get displayValue() {
        return formatDose(this.value, this.useFractions);
    }

    get unitLabel() {
        const unit = this.props.record.data.dose_unit;
        const selection = (this.props.record.fields.dose_unit || {}).selection || [];
        const found = selection.find(([key]) => key === unit);
        return found ? found[1] : "";
    }

    get isZero() {
        return !Number(this.value);
    }

    setDose(value) {
        const rounded = Math.max(0, Math.round(value * 100) / 100);
        return this.props.record.update({ [this.props.name]: rounded });
    }

    async increment(direction) {
        // Commit what is typed first, then step from it
        const input = this.inputRef.el;
        let current = Number(this.value) || 0;
        if (input && input.value !== "" && !isNaN(parseFloat(input.value))) {
            current = parseFloat(input.value);
        }
        await this.setDose(current + direction * this.step);
    }

    chipLabel(value) {
        return formatDose(value, this.useFractions);
    }
}

export const doseField = {
    ...floatField,
    component: DoseField,
    displayName: "Dose (stepper)",
    fieldDependencies: [
        { name: "dose_step", type: "float" },
        { name: "dose_quick_values", type: "char" },
        { name: "dose_fraction", type: "boolean" },
        { name: "dose_unit", type: "selection" },
    ],
};

registry.category("fields").add("hc_dose", doseField);
