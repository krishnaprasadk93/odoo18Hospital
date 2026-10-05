/** @odoo-module **/

/**
 * Auto-select content of Float input cells on focus.
 * This allows doctor to click any dose cell and immediately
 * type the value without manually selecting/deleting 0.00
 */
document.addEventListener("focusin", (e) => {
    const input = e.target;
    if (
        input.tagName === "INPUT" &&
        (input.type === "text" || input.type === "number") &&
        input.closest(".o_dose_cell, .o_field_float")
    ) {
        // Timeout ensures Odoo has finished rendering the input value
        setTimeout(() => {
            input.select();
        }, 0);
    }
});