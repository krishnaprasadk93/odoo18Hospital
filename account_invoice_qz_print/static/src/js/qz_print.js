/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

class QzInvoicePrintAction extends Component {
    static template = "account_invoice_qz_print.QzInvoicePrintAction";
    static props = { ...standardActionServiceProps };

    setup() {
        this.print();
    }

    async print() {
        try {
            const qz = await this.loadQzTray();
            await this.connectQz(qz);

            const orm = this.env.services.orm;
            const printers = await orm.searchRead(
                "qz.printer",
                [["is_default", "=", true]],
                ["name"]
            );
            const printer = printers.length ? printers[0] : null;

            // If no printer is configured, warn or use default system printer
            const config = qz.configs.create(printer ? printer.name : null);

            const escposRaw = this.props.action.context.escpos_raw;

            const data = [{
                type: "raw",
                format: "plain",
                data: escposRaw,
                options: { language: "ESCPOS" }
            }];

            await qz.print(config, data);

            // Close the action automatically after printing
            this.props.action.doAction({ type: "ir.actions.act_window_close" });
        } catch (error) {
            console.error("QZ Print Error:", error);
            // Optional: Show a notification service error here if you want
        }
    }

    async loadQzTray() {
        if (window.qz) {
            return window.qz;
        }
        await new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = "https://demo.qz.io/js/qz-tray.js";
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
        return window.qz;
    }

    async connectQz(qz) {
        if (!qz.websocket.isActive()) {
            await qz.websocket.connect();
        }
    }
}

// We need a minimal template for the component, even if empty
// But creating a separate XML file is annoying if you just deleted it.
// SOLUTION: Use xml`` helper or define a simple inline template if permitted,
// BUT Odoo 18 strictly prefers XML files.
// However, 'client actions' can also be simple functions. Let's try the FUNCTION approach first
// because it is simpler and requires no XML.

// ---------------
// OPTION B: FUNCTION-BASED ACTION (Simpler, No XML needed)
// ---------------

async function qzInvoicePrintAction(env, action) {
    // Helper to load QZ
    const loadQz = async () => {
        if (window.qz) return window.qz;
        await new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = "https://demo.qz.io/js/qz-tray.js";
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
        return window.qz;
    };

    try {
        const qz = await loadQz();
        if (!qz.websocket.isActive()) {
            await qz.websocket.connect();
        }

        const orm = env.services.orm;
        const printers = await orm.searchRead(
            "qz.printer",
            [["is_default", "=", true]],
            ["name"]
        );
        const printerName = printers.length ? printers[0].name : null;

        const config = qz.configs.create(printerName);
        const escposRaw = action.context.escpos_raw;

        const data = [{
            type: "raw",
            format: "plain",
            data: escposRaw,
            options: { language: "ESCPOS" }
        }];

        await qz.print(config, data);

        // Return 'true' or next action to close nicely
        return { type: "ir.actions.act_window_close" };

    } catch (err) {
        console.error("QZ Print Failed", err);
        // env.services.notification.add("Printing Failed: " + err.message, { type: "danger" });
    }
}

registry.category("actions").add("qz_invoice_print", qzInvoicePrintAction);
