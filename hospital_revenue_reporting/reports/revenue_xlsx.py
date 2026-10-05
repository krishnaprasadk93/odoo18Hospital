from odoo import models


class HospitalRevenueXlsx(models.AbstractModel):
    _name = 'report.hospital_revenue_reporting.revenue_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards[0]

        sheet = workbook.add_worksheet('Revenue Report')

        # Define formats
        header = workbook.add_format(
            {'bold': True, 'align': 'center', 'bg_color': '#2F5597', 'color': 'white', 'border': 1})
        money = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text = workbook.add_format({'border': 1})
        total_fmt = workbook.add_format({'bold': True, 'num_format': '₹#,##0.00', 'border': 1})

        # Credit note format (red for negative values)
        credit_money = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'color': 'red'})

        # Summary formats
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'left',
            'bg_color': '#D9E1F2', 'border': 1
        })
        summary_label = workbook.add_format({'bold': True, 'align': 'left', 'border': 1})
        summary_value = workbook.add_format({'align': 'left', 'border': 1})
        summary_money = workbook.add_format({'num_format': '#,##0.00', 'border': 1})

        # Get invoices and credit notes
        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', wizard.date_from),
            ('invoice_date', '<=', wizard.date_to),
        ]

        moves = self.env['account.move'].search(domain, order='invoice_date, name')

        # ==================== SUMMARY SECTION ====================
        all_journals = set()
        unique_patients = set()
        total_revenue = 0
        total_credit_notes = 0
        journal_collection = {}
        journal_refunds = {}
        total_collected = 0
        total_refunded = 0

        for m in moves:
            unique_patients.add(m.partner_id.id)

            if m.move_type == 'out_invoice':
                total_revenue += m.amount_total
            elif m.move_type == 'out_refund':
                total_credit_notes += m.amount_total

            if m.payment_state in ['paid', 'in_payment']:
                receivable_line = m.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'
                )

                if m.move_type == 'out_invoice':
                    # For invoices: matched_credit_ids = payments received
                    partials = receivable_line.matched_credit_ids

                    for partial in partials:
                        counterpart_line = partial.credit_move_id
                        journal_name = counterpart_line.move_id.journal_id.name
                        amount = partial.amount

                        if journal_name:
                            all_journals.add(journal_name)
                            if journal_name not in journal_collection:
                                journal_collection[journal_name] = 0
                            journal_collection[journal_name] += amount
                            total_collected += amount

                elif m.move_type == 'out_refund':
                    # For credit notes: matched_debit_ids = refunds paid
                    partials = receivable_line.matched_debit_ids

                    for partial in partials:
                        counterpart_line = partial.debit_move_id
                        journal_name = counterpart_line.move_id.journal_id.name
                        amount = partial.amount

                        if journal_name:
                            all_journals.add(journal_name)
                            if journal_name not in journal_refunds:
                                journal_refunds[journal_name] = 0
                            journal_refunds[journal_name] += amount
                            total_refunded += amount

        sorted_journals = sorted(list(all_journals))

        # Write summary section
        row = 0
        sheet.merge_range(row, 0, row, 3, 'REVENUE SUMMARY REPORT', title_fmt)
        row += 1

        sheet.write(row, 0, 'Date Range:', summary_label)
        date_range_str = f"{wizard.date_from.strftime('%d-%m-%Y')} to {wizard.date_to.strftime('%d-%m-%Y')}"
        sheet.merge_range(row, 1, row, 3, date_range_str, summary_value)
        row += 1

        sheet.write(row, 0, 'Total Revenue:', summary_label)
        sheet.write(row, 1, total_revenue, summary_money)
        row += 1

        sheet.write(row, 0, 'Total Credit Notes:', summary_label)
        sheet.write(row, 1, total_credit_notes, summary_money)
        row += 1

        net_revenue = total_revenue - total_credit_notes
        sheet.write(row, 0, 'Net Revenue:', summary_label)
        sheet.write(row, 1, net_revenue, summary_money)
        row += 1

        sheet.write(row, 0, 'Total Patient Visits:', summary_label)
        sheet.write(row, 1, len(unique_patients), summary_value)
        row += 2

        sheet.merge_range(row, 0, row, 3, 'COLLECTION SUMMARY', title_fmt)
        row += 1

        sheet.write(row, 0, 'Total Collection:', summary_label)
        sheet.write(row, 1, total_collected, summary_money)
        row += 1

        for journal_name in sorted_journals:
            collected = journal_collection.get(journal_name, 0)
            sheet.write(row, 0, f'{journal_name}:', summary_label)
            sheet.write(row, 1, collected, summary_money)
            row += 1

        row += 1
        sheet.write(row, 0, 'Total Refunds:', summary_label)
        sheet.write(row, 1, total_refunded, summary_money)
        row += 1

        for journal_name in sorted_journals:
            refunded = journal_refunds.get(journal_name, 0)
            if refunded > 0:
                sheet.write(row, 0, f'{journal_name} (Refund):', summary_label)
                sheet.write(row, 1, refunded, summary_money)
                row += 1

        net_collected = total_collected - total_refunded
        sheet.write(row, 0, 'Net Collection:', summary_label)
        sheet.write(row, 1, net_collected, summary_money)
        row += 1

        pending_amount = net_revenue - net_collected
        sheet.write(row, 0, 'Pending/Unpaid:', summary_label)
        sheet.write(row, 1, pending_amount, summary_money)
        row += 2

        # ==================== DETAILED DATA SECTION ====================
        headers = ['Date', 'Type', 'Invoice/CN', 'Patient', 'Doctor',
                   'Consultation (₹)', 'Medicines (₹)', 'Procedures (₹)', 'Return Amount (₹)']

        for journal_name in sorted_journals:
            headers.append(f'{journal_name} (₹)')

        headers.append('Amount Collected (₹)')
        headers.append('Balance Returned (₹)')

        for col, h in enumerate(headers):
            sheet.write(row, col, h, header)

        row += 1

        # Track column totals
        total_consult = 0
        total_medicine = 0
        total_other = 0
        total_return = 0
        total_collected_col = 0
        total_balance_col = 0
        journal_col_totals = {j: 0 for j in sorted_journals}

        for m in moves:
            is_credit_note = m.move_type == 'out_refund'

            # Logic to split invoice amount types
            consult_amt = 0
            medicine_amt = 0
            other_amt = 0
            return_amt = 0

            # Safe access to ticket
            ticket = getattr(m, 'op_ticket_id', False)
            doctor_name = ticket.doctor_id.name if ticket else ''

            if is_credit_note:
                # For credit notes, show as return amount
                return_amt = m.amount_total
            else:
                # Logic for splitting amounts (invoices only)
                is_consultation = False
                if ticket and hasattr(ticket, 'consultation_invoice_id') and ticket.consultation_invoice_id.id == m.id:
                    is_consultation = True

                if is_consultation:
                    consult_amt = m.amount_total
                else:
                    for line in m.invoice_line_ids:
                        if hasattr(line.product_id, 'is_medicine') and line.product_id.is_medicine:
                            medicine_amt += line.price_subtotal
                        else:
                            other_amt += line.price_subtotal

            # --- PAYMENT LOGIC ---
            row_journal_amounts = {j: 0 for j in sorted_journals}

            if m.payment_state in ['paid', 'in_payment']:
                receivable_line = m.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'
                )

                if m.move_type == 'out_invoice':
                    # For invoices: payments received
                    partials = receivable_line.matched_credit_ids

                    for partial in partials:
                        counterpart_line = partial.credit_move_id
                        j_name = counterpart_line.move_id.journal_id.name
                        amount = partial.amount

                        if j_name and j_name in row_journal_amounts:
                            row_journal_amounts[j_name] += amount

                elif m.move_type == 'out_refund':
                    # For credit notes: refunds paid (show as negative)
                    partials = receivable_line.matched_debit_ids

                    for partial in partials:
                        counterpart_line = partial.debit_move_id
                        j_name = counterpart_line.move_id.journal_id.name
                        amount = partial.amount

                        if j_name and j_name in row_journal_amounts:
                            row_journal_amounts[j_name] -= amount  # Negative for refund

            # Writing Row
            col = 0
            sheet.write(row, col, str(m.invoice_date), text)
            col += 1

            doc_type = 'Credit Note' if is_credit_note else 'Invoice'
            sheet.write(row, col, doc_type, text)
            col += 1

            sheet.write(row, col, m.name, text)
            col += 1
            sheet.write(row, col, m.partner_id.name, text)
            col += 1
            sheet.write(row, col, doctor_name, text)
            col += 1

            # Use credit_money format for credit notes
            amt_format = credit_money if is_credit_note else money

            sheet.write(row, col, consult_amt if not is_credit_note else 0, amt_format)
            col += 1
            sheet.write(row, col, medicine_amt if not is_credit_note else 0, amt_format)
            col += 1
            sheet.write(row, col, other_amt if not is_credit_note else 0, amt_format)
            col += 1
            sheet.write(row, col, return_amt, credit_money if return_amt > 0 else money)
            col += 1

            # Write Payment Columns
            for journal_name in sorted_journals:
                amt = row_journal_amounts.get(journal_name, 0)
                sheet.write(row, col, amt, credit_money if amt < 0 else money)
                journal_col_totals[journal_name] += amt
                col += 1

            amount_collected = m.amount_collected if not is_credit_note else 0
            balance_amount = m.balance_amount if not is_credit_note else 0
            sheet.write(row, col, amount_collected, money)
            col += 1
            sheet.write(row, col, balance_amount, money)
            col += 1

            total_consult += consult_amt
            total_medicine += medicine_amt
            total_other += other_amt
            total_return += return_amt
            total_collected_col += amount_collected
            total_balance_col += balance_amount
            row += 1

        # Write Footer Totals
        col = 0
        sheet.write(row, col, 'TOTAL', header)
        sheet.write(row, 1, '', text)
        sheet.write(row, 2, '', text)
        sheet.write(row, 3, '', text)
        sheet.write(row, 4, '', text)

        col = 5
        sheet.write(row, col, total_consult, total_fmt)
        col += 1
        sheet.write(row, col, total_medicine, total_fmt)
        col += 1
        sheet.write(row, col, total_other, total_fmt)
        col += 1
        sheet.write(row, col, total_return, total_fmt)
        col += 1

        for journal_name in sorted_journals:
            sheet.write(row, col, journal_col_totals[journal_name], total_fmt)
            col += 1

        sheet.write(row, col, total_collected_col, total_fmt)
        col += 1
        sheet.write(row, col, total_balance_col, total_fmt)
        col += 1
