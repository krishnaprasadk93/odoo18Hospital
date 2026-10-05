/** @odoo-module **/

import { registry } from "@web/core/registry";

const hospitalQzPrintAction = async (env, action) => {

    const params = action.params || {};
    const escposRaw = params.escpos_raw;
    const notifyData = params.notification;

    // 1️⃣ Show notification if provided
    if (notifyData) {
        env.services.notification.add(notifyData.message, {
            title: notifyData.title || "Info",
            type: notifyData.type || "success",
            sticky: notifyData.sticky || false,
        });
    }

    // 2️⃣ Load QZ dynamically (IMPORTANT)
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

    if (escposRaw) {
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
            const printer = printers.length ? printers[0] : null;

            // If no printer is configured, warn or use default system printer
            const config = qz.configs.create(printer ? printer.name : null);
           // const config = qz.configs.create(null); // default printer

            const data = [{
                type: "raw",
                format: "plain",
                data: escposRaw,
                options: { language: "ESCPOS" }
            }];

            await qz.print(config, data);

            console.log("Hospital QZ Print: Success");

        } catch (err) {
            console.error("QZ Print Error:", err);
            env.services.notification.add(
                "Printing Failed: " + err.message,
                {
                    title: "Print Error",
                    type: "danger",
                    sticky: true,
                }
            );
        }
    }

    return { type: "ir.actions.act_window_close" };
};

registry.category("actions").add("hospital_qz_print", hospitalQzPrintAction);
