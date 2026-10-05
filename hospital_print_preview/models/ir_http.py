from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        show_preview = self.env['ir.config_parameter'].sudo().get_param(
            'hospital_print_preview.show_print_preview', False
        )
        result['show_print_preview'] = str(show_preview).lower() == 'true'
        return result
