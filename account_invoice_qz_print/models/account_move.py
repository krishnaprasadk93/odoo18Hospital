from odoo import models
import textwrap
import base64
import struct
from PIL import Image, ImageOps
import io


class AccountMove(models.Model):
    _inherit = "account.move"

    def _escpos_line(self, text=""):
        return (text or "") + "\x0A"

    def _escpos(self, text="", align="left", font="A", bold=False, double_h=False, double_w=False):
        """Helper to format a single line or text segment."""
        cmds = []

        # Alignment
        if align == "center":
            cmds.append("\x1B\x61\x01")
        elif align == "right":
            cmds.append("\x1B\x61\x02")
        else:
            cmds.append("\x1B\x61\x00")

        # Font & Size
        # ESC ! n (Master print mode)
        # Bit 4: Double Height, Bit 5: Double Width, Bit 3: Bold
        mode = 0
        if font == "B": mode |= 1  # Font B (small)
        if bold: mode |= 8  # Bold
        if double_h: mode |= 16  # Double Height
        if double_w: mode |= 32  # Double Width
        cmds.append(f"\x1B\x21{chr(mode)}")

        cmds.append(text)
        return "".join(cmds)

    def _build_escpos_invoice_at301_old(self):
        """Design: VSS Medicare Style with Dynamic Payment Info"""
        self.ensure_one()
        parts = []

        # --- 1. HEADER ---
        parts.append(self._escpos("VSS Medicare\n", align="center", bold=True, double_h=True, double_w=True))

        company = self.company_id
        if company.city:
            parts.append(self._escpos(f"{company.city}, {company.state_id.name or ''}\n", align="center", bold=True))
        if company.phone:
            parts.append(self._escpos(f"Ph: {company.phone}\n", align="center"))

        parts.append(self._escpos("\n", align="left"))

        # --- 2. PATIENT DETAILS ---
        partner = self.partner_id
        p_name = partner.name[:15] if partner.name else ""
        p_age = "38"  # Replace with partner.age if available

        line1 = f"Patient Name : {p_name:<10} "
        parts.append(self._escpos(line1 + "\n", align="left", bold=True))

        p_addr = (partner.city or "")[:12]
        p_phone = (partner.phone or "")[:12]
        line2 = f"Address : {p_addr:<12} Ph: {p_phone}"
        parts.append(self._escpos(line2 + "\n", align="left", bold=True))

        # Doctor (Safe Access)
        doc_name = "Dr.Sandeep.V.S"
        if hasattr(self, 'op_ticket_id') and self.op_ticket_id:
            if self.op_ticket_id.doctor_id:
                doc_name = self.op_ticket_id.doctor_id.name
        elif self.invoice_user_id:
            doc_name = self.invoice_user_id.name

        parts.append(self._escpos(f"\nConsulting Doctor : {doc_name}\n", align="left", bold=True))

        # ID (Safe Access)
        if hasattr(self, 'op_ticket_id') and self.op_ticket_id:
            p_seq = self.op_ticket_id.patient_id.patient_seq if self.op_ticket_id.patient_id else ""
            visit = self.op_ticket_id.visit_no or ""
            parts.append(self._escpos(f"Patient ID NO: {p_seq}\n", align="center", bold=True))
            parts.append(self._escpos(f"Patient Visit NO: {visit}\n", align="center", bold=True))
        else:
            parts.append(self._escpos(f"Invoice NO: {self.name}\n", align="center", bold=True))

        # --- 3. ITEMS ---
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Bill\n", align="center", bold=True, double_w=True))

        header = f"{'S.N':<4}{'Product':<20}{'MRP':>8}{'Qty':>4}{'Exp':>6}{'Total':>10}"
        parts.append(self._escpos(header + "\n", align="left", font="B", bold=True))

        idx = 1
        LINE_WIDTH = 42
        for line in self.invoice_line_ids:

            name = line.name or ""
            mrp = f"{line.price_unit:.2f}"
            qty = f"{line.quantity:.0f}"
            total = f"{line.price_subtotal:.2f}"

            batch = line.lot_id.name if getattr(line, "lot_id", False) else ""
            exp = line.expiry_mm_yy if getattr(line, "expiry_mm_yy", False) else ""

            # -------------------------------
            # AUTO WRAP PRODUCT NAME (max 22 chars for pricing space)
            # -------------------------------
            wrapped_name = textwrap.wrap(name, width=22)

            # First line includes pricing
            first_part = wrapped_name[0] if wrapped_name else ""

            # Price section aligned to right edge
            price_section = f"{mrp:>7}{qty:>4}{total:>9}"

            row1 = f"{idx:<3} {first_part:<22}{price_section}"
            parts.append(self._escpos(row1 + "\n", align="left", bold=True))

            # Remaining wrapped lines (if product name long)
            for extra in wrapped_name[1:]:
                parts.append(self._escpos(f"    {extra}\n", align="left"))

            # -------------------------------
            # BATCH + EXPIRY (Only If Exists)
            # -------------------------------
            if batch or exp:
                batch_line = "    "
                if batch:
                    batch_line += f"Batch: {batch}"
                if exp:
                    batch_line += f"   Exp: {exp}"

                parts.append(self._escpos(batch_line + "\n", align="left"))

            parts.append(self._escpos("\n"))

            idx += 1

        parts.append(self._escpos("-" * LINE_WIDTH + "\n", align="center"))

        # --- 4. TOTALS & PAYMENTS ---
        net_amt = f"{self.amount_total:.2f}"

        payment_vals = self._get_reconciled_invpayments()
        pay_mode = "Unpaid"

        if payment_vals:
            # Extract unique journal names
            journals = set(p['journal_name'] for p in payment_vals)
            pay_mode = ", ".join(journals)
            if len(pay_mode) > 15: pay_mode = "Mixed"
        elif self.payment_state == 'paid':
            pay_mode = "Cash"

        parts.append(self._escpos(f"{'Mode Of Pay:':>25} {pay_mode:>10}\n", align="right", bold=True))

        if payment_vals:
            parts.append(self._escpos(f"\n{'Payment Details:':>25}\n", align="right", bold=True))
            for p in payment_vals:
                # p['amount'] is the amount strictly applied to this invoice
                amt = f"{p['amount']:.2f}"
                j_name = (p['journal_name'] or "Cash")[:15]
                parts.append(self._escpos(f"{j_name:>27} {amt:>13}\n", align="right", font="B"))

        # Balance
        if self.amount_residual > 0:
            parts.append(self._escpos(f"{'Balance Due:':>25} {self.amount_residual:.2f}\n", align="right", bold=True))

        # --- 5. FOOTER ---
        parts.append(self._escpos("\nAuthorized Signatory\n", align="left"))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Get Well Soon ! Thank You !\n", align="center"))

        # Feed & Cut
        parts.append("\x0A\x0A\x0A\x0A")
        parts.append("\x1D\x56\x42\x00")

        return "".join(parts)

    def action_qz_direct_print(self):
        self.ensure_one()
        escpos_str = self._build_escpos_invoice_at301()
        return {
            "type": "ir.actions.client",
            "tag": "qz_invoice_print",
            "context": {
                "escpos_raw": escpos_str,
            },
        }

    def action_qz_direct_print1(self):
        self.ensure_one()
        # OLD CODE (Error Source):
        # report = self.env.ref("account_invoice_qz_print.report_invoice_thermal")

        # NEW CODE:
        escpos_str = self._build_escpos_invoice_at301()
        return {
            "type": "ir.actions.client",
            "tag": "qz_invoice_print",
            "context": {
                "escpos_raw": escpos_str,
            },
        }

    def action_qz_direct_print_test(self):
        self.ensure_one()
        # TEST: Pure text, no fancy hex codes first
        # Just text and newlines
        escpos_str = "--------------------------------\n" \
                     "      TEST PRINT SUCCESS        \n" \
                     "--------------------------------\n" \
                     "If you can read this,\n" \
                     "the printer is working!\n" \
                     "\n\n\n\n"  # Feed lines manually

        return {
            "type": "ir.actions.client",
            "tag": "qz_invoice_print",
            "context": {
                "escpos_raw": escpos_str,
            },
        }

    def _get_reconciled_invpayments(self):
        """Get payment details for this invoice (Odoo 18 compatible)"""
        self.ensure_one()

        payments = []

        # Find all partial reconciliations linked to this invoice
        partials = self.env['account.partial.reconcile'].search([
            '|',
            ('debit_move_id', 'in', self.line_ids.ids),
            ('credit_move_id', 'in', self.line_ids.ids)
        ])

        processed_payment_ids = set()

        for partial in partials:
            # Determine which side is the payment
            if partial.credit_move_id.move_id == self:
                payment_move = partial.debit_move_id.move_id
                amount = partial.amount
            else:
                payment_move = partial.credit_move_id.move_id
                amount = partial.amount

            # Avoid duplicates
            if payment_move.id in processed_payment_ids:
                continue

            processed_payment_ids.add(payment_move.id)

            # Build payment info dict
            payment_info = {
                'journal_name': payment_move.journal_id.name,
                'journal_type': payment_move.journal_id.type,
                'amount': amount,
                'date': payment_move.date,
                'ref': payment_move.ref or payment_move.name,
            }

            payments.append(payment_info)

        return payments

    def _build_escpos_consultaion_invoice_at301(self):
        """Design: VSS Medicare Style - Consultation/Service Invoice (No Batch/MRP/Qty/Expiry)"""
        self.ensure_one()
        parts = []

        # --- 0. COMPANY LOGO (Top Center) ---
        logo_str = self._escpos_logo(max_width=384)
        if logo_str:
            parts.append('\x1b\x61\x01')  # center align (str, not bytes)
            parts.append(logo_str)
            parts.append('\x1b\x61\x00')  # reset align

        # --- 1. HEADER ---
        parts.append(self._escpos("VSS Medicare\n", align="center", bold=True, double_h=True, double_w=True))

        company = self.company_id
        if company.city:
            parts.append(self._escpos(f"{company.city}, {company.state_id.name or ''}\n", align="center", bold=True))
        if company.phone:
            parts.append(self._escpos(f"Ph: {company.phone}\n", align="center"))

        parts.append(self._escpos("\n", align="left"))

        # --- 2. PATIENT DETAILS ---
        partner = self.partner_id
        p_name = partner.name[:20] if partner.name else ""

        parts.append(self._escpos(f"Patient Name : {p_name}\n", align="left", bold=True))

        p_addr = (partner.city or "")[:15]
        p_phone = (partner.phone or "")[:12]
        line2 = f"Address : {p_addr:<15} Ph: {p_phone}"
        parts.append(self._escpos(line2 + "\n", align="left", bold=True))

        # Doctor (Safe Access)
        doc_name = "Dr.Sandeep.V.S"
        doc_ph = ""
        if hasattr(self, 'op_ticket_id') and self.op_ticket_id:
            if self.op_ticket_id.doctor_id:
                doc_name = self.op_ticket_id.doctor_id.name
                doc_ph = self.op_ticket_id.doctor_id.work_phone
        elif self.invoice_user_id:
            doc_name = self.invoice_user_id.name

        parts.append(self._escpos(f"\nConsulting Doctor : {doc_name}\n", align="left", bold=True))
        if doc_ph:
            parts.append(self._escpos(f"                    {doc_ph}\n", align="left", bold=True))
        # ID (Safe Access)
        if hasattr(self, 'op_ticket_id') and self.op_ticket_id:
            p_seq = self.op_ticket_id.patient_id.patient_seq if self.op_ticket_id.patient_id else ""
            visit = self.op_ticket_id.visit_no or ""
            parts.append(self._escpos(f"Patient ID NO: {p_seq}\n", align="center", bold=True))
            parts.append(self._escpos(f"Patient Visit NO: {visit}\n", align="center", bold=True))
        else:
            parts.append(self._escpos(f"Invoice NO: {self.name}\n", align="center", bold=True))

        # Date & Time
        inv_date = self.invoice_date.strftime("%d-%m-%Y") if self.invoice_date else ""
        parts.append(self._escpos(f"Date: {inv_date}\n", align="center"))

        # --- 3. CONSULTATION/SERVICES SECTION ---
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Consultation Bill\n", align="center", bold=True, double_w=True))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))

        # Header for services (SL, Service, Total)
        header = f"{'SL':<4}{'Service':<25}{'Amount':>10}"
        parts.append(self._escpos(header + "\n", align="left", font="B", bold=True))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))

        idx = 1
        subtotal = 0.0

        for line in self.invoice_line_ids:
            name = line.name or line.product_id.name or "Service"
            total = line.price_subtotal
            subtotal += total

            # Auto wrap long service names (max 25 chars to fit total column)
            wrapped_name = textwrap.wrap(name, width=25)

            # First line with amount
            first_part = wrapped_name[0] if wrapped_name else name[:25]
            row1 = f"{idx:<4}{first_part:<25}{total:>10.2f}"
            parts.append(self._escpos(row1 + "\n", align="left", bold=True))

            # Remaining wrapped lines (if service name is long)
            for extra in wrapped_name[1:]:
                parts.append(self._escpos(f"    {extra}\n", align="left"))

            idx += 1

        parts.append(self._escpos("-" * 42 + "\n", align="center"))

        # --- 4. TOTALS ---
        parts.append(self._escpos(f"{'Subtotal:':>30} {subtotal:>10.2f}\n", align="right", bold=True))

        # Tax if any
        if self.amount_tax > 0:
            parts.append(self._escpos(f"{'Tax:':>30} {self.amount_tax:>10.2f}\n", align="right"))

        # Net Total
        parts.append(
            self._escpos(f"{'Net Amount:':>30} {self.amount_total:>10.2f}\n", align="right", bold=True, double_h=True))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))

        # --- 5. PAYMENT SECTION (Mode of Payment & Payment Details on Right) ---
        payment_vals = self._get_reconciled_invpayments()
        pay_mode = "Unpaid"

        if payment_vals:
            # Extract unique journal names
            journals = set(p['journal_name'] for p in payment_vals)
            pay_mode = ", ".join(journals)
            if len(pay_mode) > 15:
                pay_mode = "Mixed"
        elif self.payment_state == 'paid':
            pay_mode = "Cash"

        # Mode of Payment (Right Aligned)
        parts.append(self._escpos(f"{'Mode Of Payment:':>25} {pay_mode:>15}\n", align="right", bold=True))

        # Payment Details (Right Aligned with amounts)
        if payment_vals:
            for p in payment_vals:
                amt = f"{p['amount']:.2f}"
                j_name = (p['journal_name'] or "Cash")[:15]
                parts.append(self._escpos(f"{j_name:>27} {amt:>13}\n", align="right", font="B"))

        # Balance Due (Right Aligned)
        if self.amount_residual > 0:
            parts.append(
                self._escpos(f"{'Balance Due:':>28} {self.amount_residual:>12.2f}\n", align="right", bold=True))

        # Cash Tendered / Change (Cash payments only)
        if self.amount_collected:
            parts.append(
                self._escpos(f"{'Amount Collected:':>25} {self.amount_collected:>15.2f}\n", align="right", bold=True))
            parts.append(
                self._escpos(f"{'Balance Returned:':>25} {self.balance_amount:>15.2f}\n", align="right", bold=True))

        # --- 6. FOOTER ---
        parts.append(self._escpos("\n", align="left"))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Authorized Signatory\n", align="left"))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Thank You for Your Visit!\n", align="center", bold=True))
        parts.append(self._escpos("Get Well Soon!\n", align="center"))

        # Feed & Cut
        parts.append("\x0A\x0A\x0A\x0A")
        parts.append("\x1D\x56\x42\x00")

        return "".join(parts)

    def _build_escpos_invoice_at301(self):
        """Design: VSS Medicare Style with Dynamic Payment Info"""
        self.ensure_one()
        parts = []

        # --- 0. COMPANY LOGO (Top Center) ---
        logo_str = self._escpos_logo(max_width=384)
        if logo_str:
            parts.append('\x1b\x61\x01')  # center align (str, not bytes)
            parts.append(logo_str)
            parts.append('\x1b\x61\x00')  # reset align

        # --- 1. HEADER ---
        parts.append(self._escpos("VSS Medicare\n", align="center", bold=True, double_h=True, double_w=True))

        company = self.company_id
        if company.city:
            parts.append(self._escpos(f"{company.city}, {company.state_id.name or ''}\n", align="center", bold=True))
        if company.phone:
            parts.append(self._escpos(f"Ph: {company.phone}\n", align="center"))

        parts.append(self._escpos("\n", align="left"))

        # --- 2. PATIENT DETAILS ---
        partner = self.partner_id
        p_name = partner.name[:20] if partner.name else ""

        parts.append(self._escpos(f"Patient Name : {p_name}\n", align="left", bold=True))

        p_addr = (partner.city or "")[:15]
        p_phone = (partner.phone or "")[:12]
        line2 = f"Address : {p_addr:<15} Ph: {p_phone}"
        parts.append(self._escpos(line2 + "\n", align="left", bold=True))

        # Doctor (Safe Access)
        doc_name = "Dr.Sandeep.V.S"
        doc_ph = ""
        if hasattr(self, 'op_ticket_id') and self.op_ticket_id:
            if self.op_ticket_id.doctor_id:
                doc_name = self.op_ticket_id.doctor_id.name
                doc_ph = self.op_ticket_id.doctor_id.work_phone
        elif self.invoice_user_id:
            doc_name = self.invoice_user_id.name

        parts.append(self._escpos(f"\nConsulting Doctor : {doc_name}\n", align="left", bold=True))
        if doc_ph:
            parts.append(self._escpos(f"                    {doc_ph}\n", align="left", bold=True))
        # ID (Safe Access)
        if hasattr(self, 'op_ticket_id') and self.op_ticket_id:
            p_seq = self.op_ticket_id.patient_id.patient_seq if self.op_ticket_id.patient_id else ""
            visit = self.op_ticket_id.visit_no or ""
            parts.append(self._escpos(f"Patient ID NO: {p_seq}\n", align="left", bold=True))
            parts.append(self._escpos(f"Patient Visit NO: {visit}\n", align="left", bold=True))
        else:
            parts.append(self._escpos(f"Invoice NO: {self.name}\n", align="center", bold=True))

        # --- 3. ITEMS ---
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Bill\n", align="center", bold=True, double_w=True))

        # CORRECTED HEADER - Match your actual print output
        header = f"{'S.N':<4}{'Product':<22}{'MRP':>10}{'Qty':>4}{'Total':>8}"
        parts.append(self._escpos(header + "\n", align="left", bold=True))

        idx = 1
        LINE_WIDTH = 42
        for line in self.invoice_line_ids:

            name = line.name or ""
            mrp = f"{line.price_unit:.2f}"
            qty = f"{line.quantity:.0f}"
            total = f"{line.price_subtotal:.2f}"

            batch = line.lot_id.name if getattr(line, "lot_id", False) else ""
            exp = line.expiry_mm_yy if getattr(line, "expiry_mm_yy", False) else ""

            # AUTO WRAP PRODUCT NAME (max 22 chars for pricing space)
            wrapped_name = textwrap.wrap(name, width=22)

            # First line includes pricing
            first_part = wrapped_name[0] if wrapped_name else ""

            # Price section aligned to right edge
            price_section = f"{mrp:>10}{qty:>4}{total:>8}"

            row1 = f"{idx:<4}{first_part:<22}{price_section}"
            parts.append(self._escpos(row1 + "\n", align="left", bold=True))

            # Remaining wrapped lines (if product name long)
            for extra in wrapped_name[1:]:
                parts.append(self._escpos(f"    {extra}\n", align="left"))

            # BATCH + EXPIRY (Only If Exists)
            if batch or exp:
                batch_line = "    "
                if batch:
                    batch_line += f"Batch: {batch}"
                if exp:
                    batch_line += f"   Exp: {exp}"

                parts.append(self._escpos(batch_line + "\n", align="left"))

            idx += 1

        parts.append(self._escpos("-" * LINE_WIDTH + "\n", align="center"))

        # --- 4. TOTALS & PAYMENTS ---
        payment_vals = self._get_reconciled_invpayments()
        pay_mode = "Unpaid"

        if payment_vals:
            # Extract unique journal names
            journals = set(p['journal_name'] for p in payment_vals)
            pay_mode = ", ".join(journals)
            if len(pay_mode) > 15: pay_mode = "Mixed"
        elif self.payment_state == 'paid':
            pay_mode = "Cash"

        parts.append(self._escpos(f"{'Mode Of Pay:':>28}{pay_mode:>14}\n", align="left", bold=True))

        if payment_vals:
            for p in payment_vals:
                amt = f"{p['amount']:.2f}"
                j_name = (p['journal_name'] or "Cash")[:15]
                parts.append(self._escpos(f"{j_name:>28}{amt:>14}\n", align="left", bold=True))

        if self.amount_residual > 0:
            parts.append(self._escpos(f"{'Balance Due:':>28}{self.amount_residual:>14.2f}\n", align="left", bold=True))

        # Cash Tendered / Change (Cash payments only)
        if self.amount_collected:
            parts.append(
                self._escpos(f"{'Amount Collected:':>28}{self.amount_collected:>14.2f}\n", align="left", bold=True))
            parts.append(
                self._escpos(f"{'Balance Returned:':>28}{self.balance_amount:>14.2f}\n", align="left", bold=True))

        # --- 5. FOOTER ---
        parts.append(self._escpos("\nAuthorized Signatory\n", align="left"))
        parts.append(self._escpos("-" * 42 + "\n", align="center"))
        parts.append(self._escpos("Get Well Soon ! Thank You !\n", align="center"))

        # Feed & Cut
        parts.append("\x0A\x0A\x0A\x0A")
        parts.append("\x1D\x56\x42\x00")

        return "".join(parts)

    def _escpos_logo(self, max_width=384):
        """Returns logo as latin-1 decoded str for ESC/POS."""
        company = self.company_id
        if not company.logo:
            return ""

        try:
            img_data = base64.b64decode(company.logo)
            img = Image.open(io.BytesIO(img_data)).convert("RGBA")

            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg.convert("L")

            w, h = img.size
            if w > max_width:
                h = int(h * max_width / w)
                w = max_width
                img = img.resize((w, h), Image.LANCZOS)

            img = img.point(lambda x: 0 if x < 128 else 255, '1')
            img = ImageOps.invert(img.convert('L')).convert('1')

            if w % 8:
                new_w = w + (8 - w % 8)
                padded = Image.new('1', (new_w, h), 0)
                padded.paste(img, (0, 0))
                img = padded
                w = new_w

            xl = (w // 8) % 256
            xh = (w // 8) // 256
            yl = h % 256
            yh = h // 256

            header = b'\x1d\x76\x30\x00' + struct.pack('4B', xl, xh, yl, yh)
            raw = header + img.tobytes()

            # ✅ Decode to latin-1 str so "".join(parts) works
            return raw.decode('latin-1')

        except Exception:
            return ""

