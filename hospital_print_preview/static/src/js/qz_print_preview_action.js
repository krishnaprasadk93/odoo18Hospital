/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { PrintPreviewDialog } from "./print_preview_dialog";

const QZ_SCRIPT_URL = "https://demo.qz.io/js/qz-tray.js";

async function loadQz() {
    if (window.qz) {
        return window.qz;
    }
    await new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = QZ_SCRIPT_URL;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
    });
    return window.qz;
}

async function sendToQzTray(env, escposRaw) {
    const qz = await loadQz();
    if (!qz.websocket.isActive()) {
        await qz.websocket.connect();
    }
    const printers = await env.services.orm.searchRead(
        "qz.printer",
        [["is_default", "=", true]],
        ["name"]
    );
    const printer = printers.length ? printers[0] : null;
    const config = qz.configs.create(printer ? printer.name : null);
    const data = [{
        type: "raw",
        format: "plain",
        data: escposRaw,
        options: { language: "ESCPOS" },
    }];
    await qz.print(config, data);
}

function showNotification(env, notifyData) {
    if (!notifyData) {
        return;
    }
    env.services.notification.add(notifyData.message, {
        title: notifyData.title || "Info",
        type: notifyData.type || "success",
        sticky: notifyData.sticky || false,
    });
}

async function printOrFail(env, escposRaw, notifyData) {
    try {
        await sendToQzTray(env, escposRaw);
        showNotification(env, notifyData);
    } catch (err) {
        console.error("QZ Print Error:", err);
        env.services.notification.add("Printing Failed: " + (err.message || err), {
            title: "Print Error",
            type: "danger",
            sticky: true,
        });
    }
}

async function handlePrint(env, escposRaw, notifyData) {
    if (!escposRaw) {
        return { type: "ir.actions.act_window_close" };
    }

    if (session.show_print_preview) {
        env.services.dialog.add(PrintPreviewDialog, {
            escposRaw,
            onConfirmPrint: () => printOrFail(env, escposRaw, notifyData),
        });
    } else {
        await printOrFail(env, escposRaw, notifyData);
    }

    return { type: "ir.actions.act_window_close" };
}

const actionsRegistry = registry.category("actions");

// Overrides hospital_qz_print (hospital_qz_print module): payload in action.params.escpos_raw
actionsRegistry.add("hospital_qz_print", async (env, action) => {
    const params = action.params || {};
    return handlePrint(env, params.escpos_raw, params.notification);
}, { force: true });

// Overrides qz_invoice_print (account_invoice_qz_print module): payload in action.context.escpos_raw
actionsRegistry.add("qz_invoice_print", async (env, action) => {
    const escposRaw = action.context && action.context.escpos_raw;
    return handlePrint(env, escposRaw, null);
}, { force: true });
