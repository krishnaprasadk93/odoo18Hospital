from odoo import models, fields


class HospitalRevenueDashboard(models.Model):
    _name = 'hospital.revenue.dashboard'
    _description = 'Hospital Revenue Dashboard'
    _auto = False  # IMPORTANT → this is a SQL view

    month = fields.Char(string="Month")
    doctor_name = fields.Char(string="Doctor")
    total_revenue = fields.Float(string="Revenue")


    def init(self):
        self.env.cr.execute("""
            DROP VIEW IF EXISTS hospital_revenue_dashboard;
        """)

        self.env.cr.execute("""
            CREATE OR REPLACE VIEW hospital_revenue_dashboard AS (

                -- Monthly Revenue Trend
                SELECT
                    row_number() OVER() AS id,
                    to_char(am.invoice_date, 'YYYY-MM') AS month,
                    NULL AS doctor_name,
                    SUM(am.amount_total) AS total_revenue
                FROM account_move am
                WHERE am.move_type = 'out_invoice'
                  AND am.state = 'posted'
                  AND am.op_ticket_id IS NOT NULL
                GROUP BY month

                UNION ALL

                --  Top Doctors Revenue
                SELECT
                    row_number() OVER() AS id,
                    NULL AS month,
                    he.name AS doctor_name,
                    SUM(am.amount_total) AS total_revenue
                FROM account_move am
                JOIN hospital_op_ticket ht ON am.op_ticket_id = ht.id
                JOIN hr_employee he ON ht.doctor_id = he.id
                WHERE am.move_type = 'out_invoice'
                  AND am.state = 'posted'
                GROUP BY he.name
            )
        """)
