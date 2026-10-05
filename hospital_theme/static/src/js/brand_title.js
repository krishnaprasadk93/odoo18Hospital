/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

/**
 * Show the hospital (current company) name in the browser tab instead of
 * "Odoo", e.g. "VSS Medicare - Appointments".
 */
export const hospitalBrandTitleService = {
    dependencies: ["title"],
    start(env, { title }) {
        const name = user.activeCompany && user.activeCompany.name;
        if (name) {
            title.setParts({ brand: name });
        }
    },
};

registry.category("services").add("hospital_brand_title", hospitalBrandTitleService);
