import base64

from odoo.tests import HttpCase, tagged
from odoo.tools import file_open


@tagged('post_install', '-at_install')
class TestHospitalTheme(HttpCase):

    def test_login_page_branding(self):
        response = self.url_open('/web/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn('o_hospital_login', response.text)
        self.assertIn(self.env.company.name, response.text)
        self.assertIn('oe_login_form', response.text)  # Odoo's form is still there

    def test_clinic_app_icon(self):
        menu = self.env.ref('hospital_management.menu_hospital_root')
        self.assertEqual(menu.web_icon, 'hospital_theme,static/description/icon.png')
        self.assertTrue(menu.web_icon_data)

    def test_custom_logo_detection(self):
        Company = self.env['res.company']
        company = self.env.company
        company.logo = Company._get_logo()  # Odoo's "Your logo" placeholder
        self.assertFalse(Company.hospital_has_custom_logo(company.id))
        with file_open('hospital_theme/static/description/icon.png', 'rb') as f:
            company.logo = base64.b64encode(f.read())
        self.assertTrue(Company.hospital_has_custom_logo(company.id))
        company.logo = False
        self.assertFalse(Company.hospital_has_custom_logo(company.id))
