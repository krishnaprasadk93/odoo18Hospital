/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** A small coloured dot for a selection (ok / low / out), label as tooltip. */
export class StatusDot extends Component {
    static template = "hospital_management.StatusDot";
    static props = { ...standardFieldProps };

    get value() {
        return this.props.record.data[this.props.name];
    }

    get label() {
        const selection = this.props.record.fields[this.props.name].selection || [];
        const found = selection.find(([key]) => key === this.value);
        return found ? found[1] : "";
    }
}

registry.category("fields").add("hc_status_dot", {
    component: StatusDot,
    displayName: "Status dot",
    supportedTypes: ["selection"],
});
