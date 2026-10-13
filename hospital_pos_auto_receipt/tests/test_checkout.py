from datetime import timedelta

from odoo import fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCheckout(TransactionCase):
    """ Pharmacy / OTC checkout: Confirm, Confirm and Pay and the Split
    Payment window (batches, expiry, journals, negative stock, vouchers). """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.has_received_warning_stock_sms = True
        Journal = cls.env['account.journal']
        cls.cash_journal = Journal.create({'name': 'Test Cash', 'code': 'TCSH', 'type': 'cash'})
        cls.card_journal = Journal.create({'name': 'Test Card', 'code': 'TCRD', 'type': 'bank'})
        cls.upi_journal = Journal.create({'name': 'Test UPI', 'code': 'TUPI', 'type': 'bank'})
        cls.company.write({
            'hospital_cash_journal_id': cls.cash_journal.id,
            'hospital_card_journal_id': cls.card_journal.id,
            'hospital_upi_journal_id': cls.upi_journal.id,
            'sale_allow_negative_stock': True,
        })
        cls.env['ir.config_parameter'].sudo().set_param('hospital.require_amount_collected_entry', 'False')
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.partner = cls.env['res.partner'].create({'name': 'Checkout Test Patient'})
        cls.medicine = cls.env['product.product'].create({
            'name': 'Checkout Test Medicine',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
            'is_medicine': True,
            'list_price': 100.0,
            'taxes_id': [(6, 0, [])],
        })

    # ------------------------------------------------------------ helpers
    def _order(self, qty=2, lot=None):
        line = {'product_id': self.medicine.id, 'product_uom_qty': qty, 'price_unit': 100.0, 'tax_id': [(6, 0, [])]}
        if lot:
            line['lot_id'] = lot.id
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'order_line': [(0, 0, line)],
        })

    def _lot(self, name='TB-OK', days=365):
        return self.env['stock.lot'].create({
            'name': name,
            'product_id': self.medicine.id,
            'company_id': self.company.id,
            'expiration_date': fields.Datetime.now() + timedelta(days=days),
        })

    def _split_wizard(self, order, **vals):
        return self.env['split.payment.wizard'].with_context(
            active_id=order.id, active_ids=order.ids, active_model='sale.order').create(vals)

    def _payments(self, order):
        return self.env['account.payment'].search([('partner_id', '=', self.partner.id)]).filtered(
            lambda p: order.invoice_ids & p.reconciled_invoice_ids)

    # ------------------------------------------------------------ missing batch
    def test_missing_batch_opens_popup_from_both_buttons(self):
        order = self._order()
        pay = order.action_open_split_payment()
        self.assertEqual(pay['res_model'], 'sale.missing.batch.wizard')
        self.assertEqual(pay['context']['default_next_step'], 'pay')
        confirm = order.action_confirm_check_batch()
        self.assertEqual(confirm['res_model'], 'sale.missing.batch.wizard')
        self.assertEqual(confirm['context']['default_next_step'], 'confirm')
        self.assertEqual(order.state, 'draft')

    def test_blank_batch_no_is_rejected(self):
        order = self._order()
        action = order.action_open_split_payment()
        wizard = self.env['sale.missing.batch.wizard'].with_context(action['context']).create({})
        with self.assertRaises(UserError):
            wizard.action_create_batches()
        self.assertFalse(self.env['stock.lot'].search([('product_id', '=', self.medicine.id)]))

    def test_create_batch_and_confirm(self):
        order = self._order()
        action = order.action_confirm_check_batch()
        wizard = self.env['sale.missing.batch.wizard'].with_context(action['context']).create({})
        wizard.line_ids.write({'lot_name': ' NEWB1 '})
        wizard.action_create_batches()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.order_line.lot_id.name, 'NEWB1')

    def test_split_payment_without_batch_offers_create_batch(self):
        order = self._order()
        wizard = self._split_wizard(order)
        with self.assertRaises(RedirectWarning) as caught:
            wizard.action_create_invoice_payment()
        self.assertEqual(caught.exception.args[1]['res_model'], 'sale.missing.batch.wizard')
        self.assertEqual(order.state, 'draft')

    # Expired batches are covered by test_expired_batch.py.

    # ------------------------------------------------------------ full checkout
    def test_cash_checkout_goes_negative_and_pays(self):
        """ Create the batch from the popup, then pay in cash: delivery done
        without stock (batch goes negative), invoice paid, one cash voucher. """
        order = self._order(qty=2)
        action = order.action_open_split_payment()
        batch_wizard = self.env['sale.missing.batch.wizard'].with_context(action['context']).create({})
        batch_wizard.line_ids.write({'lot_name': 'NEWB2'})
        pay_action = batch_wizard.action_create_batches()
        self.assertEqual(pay_action['res_model'], 'split.payment.wizard')

        wizard = self.env['split.payment.wizard'].with_context(pay_action['context']).create({})
        self.assertEqual(wizard.cash_journal_id, self.cash_journal)
        self.assertEqual(wizard.card_journal_id, self.card_journal)
        self.assertEqual(wizard.upi_journal_id, self.upi_journal)
        self.assertEqual(wizard.cash_amount, 200.0)
        wizard.amount_given = 500.0
        result = wizard.action_create_invoice_payment()

        self.assertEqual(result['tag'], 'hospital_qz_print')
        picking = order.picking_ids
        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.move_line_ids.lot_id.name, 'NEWB2')
        lot = order.order_line.lot_id
        quant_qty = sum(self.env['stock.quant'].search([
            ('lot_id', '=', lot.id), ('location_id.usage', '=', 'internal')]).mapped('quantity'))
        self.assertEqual(quant_qty, -2.0)

        invoice = order.invoice_ids
        self.assertEqual(invoice.state, 'posted')
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        payments = self._payments(order)
        self.assertEqual(payments.journal_id, self.cash_journal)
        self.assertEqual(sum(payments.mapped('amount')), 200.0)
        self.assertEqual(invoice.amount_collected, 500.0)
        self.assertEqual(invoice.balance_amount, 300.0)
        self.assertTrue(invoice.is_cash_payment)

    def test_mixed_payment_creates_one_voucher_per_method(self):
        order = self._order(qty=2, lot=self._lot())
        wizard = self._split_wizard(order)
        wizard.card_amount = 50.0
        wizard._onchange_split_amounts()
        self.assertEqual(wizard.cash_amount, 150.0)
        self.assertEqual(wizard.amount_given, 150.0)
        wizard.action_create_invoice_payment()

        payments = self._payments(order)
        by_journal = {p.journal_id: p.amount for p in payments}
        self.assertEqual(by_journal, {self.cash_journal: 150.0, self.card_journal: 50.0})
        self.assertFalse(self.upi_journal in by_journal)
        self.assertIn(order.invoice_ids.payment_state, ('paid', 'in_payment'))
        self.assertFalse(order.invoice_ids.is_cash_payment)

    # ------------------------------------------------------------ journals / amount collected
    def test_amount_without_journal_is_blocked(self):
        self.company.hospital_upi_journal_id = False
        order = self._order(qty=2, lot=self._lot())
        wizard = self._split_wizard(order)
        self.assertFalse(wizard.upi_journal_id)
        wizard.upi_amount = 20.0
        wizard._onchange_split_amounts()
        with self.assertRaises(UserError):
            wizard.action_create_invoice_payment()
        self.assertEqual(order.state, 'draft')
        self.assertFalse(order.invoice_ids)

    def test_amount_given_required_when_setting_enabled(self):
        self.env['ir.config_parameter'].sudo().set_param('hospital.require_amount_collected_entry', 'True')
        order = self._order(qty=1, lot=self._lot())
        wizard = self._split_wizard(order, amount_given=0.0)
        with self.assertRaises(UserError):
            wizard.action_create_invoice_payment()
        self.assertEqual(order.state, 'draft')
