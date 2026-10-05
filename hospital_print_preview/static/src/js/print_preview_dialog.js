/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { parseEscposToLines, lineFontSize } from "./escpos_parser";

export class PrintPreviewDialog extends Component {
    static template = "hospital_print_preview.PrintPreviewDialog";
    static components = { Dialog };
    static props = {
        escposRaw: String,
        onConfirmPrint: Function,
        close: Function,
    };

    setup() {
        this.lines = parseEscposToLines(this.props.escposRaw).map((line, index) => ({
            ...line,
            key: index,
            style: this._lineStyle(line),
        }));
        this.state = { printing: false };
    }

    _lineStyle(line) {
        const parts = [`text-align:${line.align}`, `font-size:${lineFontSize(line)}px`];
        if (line.bold) {
            parts.push("font-weight:700");
        }
        return parts.join(";");
    }

    async onPrintClick() {
        this.state.printing = true;
        try {
            await this.props.onConfirmPrint();
        } finally {
            this.props.close();
        }
    }

    onCancelClick() {
        this.props.close();
    }
}
