/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

function medicineId(value) {
    return value ? (value.id !== undefined ? value.id : value[0]) : false;
}

/**
 * One-tap chips with the doctor's most prescribed medicines. Tapping a chip
 * adds a prescription line with that medicine (unsaved, like "Add a line").
 */
export class QuickMedicines extends Component {
    static template = "hospital_management.QuickMedicines";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ medicines: [], adding: false, added: [] });
        onWillStart(() => this.load());
        // Re-render the chips when lines are added / removed / changed
        useRecordObserver((record) => {
            this.state.added = record.data.prescription_ids.records
                .map((line) => medicineId(line.data.medicine_id))
                .filter(Boolean);
        });
    }

    async load() {
        const record = this.props.record;
        if (!record.resId) {
            return;
        }
        this.state.medicines = await this.orm.call("hospital.op.ticket", "get_quick_medicines", [[record.resId]]);
    }

    get lines() {
        return this.props.record.data.prescription_ids;
    }

    isAdded(medicine) {
        return this.state.added.includes(medicine.id);
    }

    async add(medicine) {
        if (this.state.adding || this.props.readonly) {
            return;
        }
        this.state.adding = true;
        try {
            const line = await this.lines.addNewRecord({
                position: "bottom",
                context: { default_medicine_id: medicine.id },
            });
            // A new untouched line is dropped by the list when the doctor moves on;
            // setting the medicine explicitly makes it a real (kept) line.
            const value = line && line.data.medicine_id;
            if (value) {
                await line.update({ medicine_id: Array.isArray(value) ? [...value] : { ...value } });
            }
        } finally {
            this.state.adding = false;
        }
    }
}

registry.category("view_widgets").add("hc_quick_medicines", {
    component: QuickMedicines,
});
