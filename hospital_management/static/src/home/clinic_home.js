/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Clinic home: quick tiles with live counts (Today's Queue, Register Patient,
 * My Queue, Pharmacy Queue, Low Stock), limited to what the user can open.
 */
export class ClinicHome extends Component {
    static template = "hospital_management.ClinicHome";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ tiles: [], user: "", loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        const data = await this.orm.call("hospital.op.ticket", "get_clinic_home_data", []);
        Object.assign(this.state, data, { loading: false });
    }

    get greeting() {
        const hour = new Date().getHours();
        return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    }

    get dateText() {
        return new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    }

    async open(tile) {
        const options = tile.context ? { additionalContext: tile.context } : {};
        if (tile.new) {
            const action = await this.action.loadAction(tile.action);
            return this.action.doAction({ ...action, views: [[false, "form"]], view_mode: "form", target: "current" });
        }
        return this.action.doAction(tile.action, options);
    }
}

registry.category("actions").add("hospital_clinic_home", ClinicHome);
