/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Show the hospital (current company) name in the browser tab instead of
 * "Odoo", after the page name: "My Consultations - VSS Medicare".
 */
export const hospitalBrandTitleService = {
    dependencies: ["title", "company"],
    start(env, { title, company }) {
        const name = company.currentCompany && company.currentCompany.name;
        if (!name) {
            return;
        }
        // Title parts are joined in insertion order: re-append the brand after
        // every update so it always comes last.
        const setParts = title.setParts;
        title.setParts = (parts) => {
            setParts({ ...parts, brand: false });
            setParts({ brand: name });
        };
        title.setParts({});
    },
};

registry.category("services").add("hospital_brand_title", hospitalBrandTitleService);
