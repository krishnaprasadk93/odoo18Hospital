/** @odoo-module **/

import { registry } from "@web/core/registry";
import { RedirectWarningDialog, WarningDialog } from "@web/core/errors/error_dialogs";

// Clinic blocking messages (hospital_management/exceptions.py) carry their own
// title, e.g. "Expired batch", instead of Odoo's generic "Invalid Operation".

export class ClinicErrorDialog extends WarningDialog {
    inferTitle() {
        return this.props.data?.context?.title || super.inferTitle();
    }
}

export class ClinicRedirectWarningDialog extends RedirectWarningDialog {
    setup() {
        super.setup();
        this.title = this.props.data?.context?.title || this.title;
    }
}

registry.category("error_dialogs")
    .add("clinic_error", ClinicErrorDialog)
    .add("clinic_redirect_warning", ClinicRedirectWarningDialog);
