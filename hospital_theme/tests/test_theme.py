from odoo.tests import HttpCase, tagged


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
