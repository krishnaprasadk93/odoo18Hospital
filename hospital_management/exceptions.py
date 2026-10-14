from odoo.exceptions import RedirectWarning, UserError


class ClinicError(UserError):
    """ A blocking message with its own title (e.g. "Expired batch") instead of
    Odoo's generic "Invalid Operation". The title travels in the error context
    and is shown by the clinic_error dialog (static/src/js/clinic_error_dialog.js). """

    def __init__(self, title, message):
        super().__init__(message)
        self.context = {'exception_class': 'clinic_error', 'title': title}


class ClinicRedirectWarning(RedirectWarning):
    """ RedirectWarning (message + one action button) with its own title. """

    def __init__(self, title, message, action, button_text):
        super().__init__(message, action, button_text)
        self.context = {'exception_class': 'clinic_redirect_warning', 'title': title}
