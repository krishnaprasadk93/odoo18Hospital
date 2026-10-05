/** @odoo-module **/

/**
 * Very small ESC/POS -> preview-line parser.
 *
 * It understands exactly the subset of commands emitted by the
 * `_escpos()` / `_escpos_logo()` helpers in account_invoice_qz_print
 * (alignment, bold/double-height/double-width/font-B, the raster bit-image
 * header, and the paper-cut command) and turns the raw string into an
 * array of { text, align, bold, doubleH, doubleW, small } lines that the
 * preview dialog can render as styled HTML approximating the printed page.
 */

const ESC = "\x1B";
const GS = "\x1D";
const ALIGN_LEFT = ESC + "\x61\x00";
const ALIGN_CENTER = ESC + "\x61\x01";
const ALIGN_RIGHT = ESC + "\x61\x02";
const MODE_PREFIX = ESC + "\x21";
const LOGO_HEADER = GS + "\x76\x30\x00";
const CUT_CMD = GS + "\x56\x42\x00";

function stripLogoBlock(raw) {
    const idx = raw.indexOf(LOGO_HEADER);
    if (idx === -1) {
        return { text: raw, hadLogo: false };
    }
    const xl = raw.charCodeAt(idx + 4) || 0;
    const xh = raw.charCodeAt(idx + 5) || 0;
    const yl = raw.charCodeAt(idx + 6) || 0;
    const yh = raw.charCodeAt(idx + 7) || 0;
    const widthBytes = xl + xh * 256;
    const height = yl + yh * 256;
    const dataLen = widthBytes * height;
    const blockEnd = idx + 8 + dataLen;
    const before = raw.slice(0, idx);
    const after = raw.slice(blockEnd);
    return { text: before + "\n[LOGO]\n" + after, hadLogo: true };
}

export function parseEscposToLines(raw) {
    if (!raw) {
        return [];
    }

    let text = stripLogoBlock(raw).text;
    text = text.split(CUT_CMD).join("");

    const rawLines = text.split("\x0A");
    const lines = [];

    for (const rawLine of rawLines) {
        let remaining = rawLine;
        let align = "left";
        let bold = false;
        let doubleH = false;
        let doubleW = false;
        let small = false;

        let matched = true;
        while (matched) {
            matched = false;
            if (remaining.startsWith(ALIGN_LEFT)) {
                align = "left";
                remaining = remaining.slice(ALIGN_LEFT.length);
                matched = true;
            } else if (remaining.startsWith(ALIGN_CENTER)) {
                align = "center";
                remaining = remaining.slice(ALIGN_CENTER.length);
                matched = true;
            } else if (remaining.startsWith(ALIGN_RIGHT)) {
                align = "right";
                remaining = remaining.slice(ALIGN_RIGHT.length);
                matched = true;
            } else if (remaining.startsWith(MODE_PREFIX)) {
                const mode = remaining.charCodeAt(MODE_PREFIX.length) || 0;
                small = !!(mode & 1);
                bold = !!(mode & 8);
                doubleH = !!(mode & 16);
                doubleW = !!(mode & 32);
                remaining = remaining.slice(MODE_PREFIX.length + 1);
                matched = true;
            }
        }

        // eslint-disable-next-line no-control-regex
        remaining = remaining.replace(/[\x00-\x08\x0B-\x1F]/g, "");

        lines.push({ text: remaining, align, bold, doubleH, doubleW, small });
    }

    return lines;
}

export function lineFontSize(line) {
    if (line.doubleH && line.doubleW) {
        return 20;
    }
    if (line.doubleH || line.doubleW) {
        return 17;
    }
    if (line.small) {
        return 10;
    }
    return 12;
}
