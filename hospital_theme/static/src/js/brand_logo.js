/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Company logo branding: when the current company has its own logo (not Odoo's
 * "Your logo" placeholder), expose it as the
 * CSS variable --hospital-logo and add `o_hospital_has_logo` on <body>. The
 * stylesheet then shows it in the navbar, behind the Clinic home / queue boards
 * (watermark) and on empty pages. Without a logo nothing changes.
 */
export const hospitalBrandLogoService = {
    dependencies: ["company", "orm"],
    async start(env, { company, orm }) {
        const companyId = company.currentCompany && company.currentCompany.id;
        if (!companyId) {
            return;
        }
        let hasLogo = false;
        try {
            hasLogo = await orm.call("res.company", "hospital_has_custom_logo", [companyId]);
        } catch {
            return;
        }
        if (!hasLogo) {
            return;
        }
        const root = document.documentElement;
        root.style.setProperty("--hospital-logo", `url("/web/image/res.company/${companyId}/logo")`);
        document.body.classList.add("o_hospital_has_logo");
    },
};

registry.category("services").add("hospital_brand_logo", hospitalBrandLogoService);
