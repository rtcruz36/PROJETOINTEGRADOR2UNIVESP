"""Custom Djoser e-mail classes for the accounts app."""

from urllib.parse import urljoin

from django.conf import settings

from djoser import email as djoser_email


class ActivationEmail(djoser_email.ActivationEmail):
    """Activation e-mail using the project's default configuration."""

    template_name = 'accounts/email/activation.html'

    def get_context_data(self):
        context = super().get_context_data()
        frontend_base_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        activation_path_template = settings.DJOSER.get('ACTIVATION_URL', '')

        uid = context.get('uid')
        token = context.get('token')
        if activation_path_template and uid and token:
            activation_path = activation_path_template.format(uid=uid, token=token)
        else:
            activation_path = context.get('url', '')

        if frontend_base_url:
            base_url = f'{frontend_base_url}/'
        else:
            protocol = context.get('protocol', 'http')
            domain = context.get('domain', '')
            base_url = f'{protocol}://{domain}/' if domain else ''

        activation_url = urljoin(base_url, activation_path)
        context['activation_url'] = activation_url
        context['frontend_activation_url'] = activation_url
        return context


class ConfirmationEmail(djoser_email.ConfirmationEmail):
    """Confirmation e-mail used after account activation."""


class PasswordResetEmail(djoser_email.PasswordResetEmail):
    """Password reset e-mail that includes the reset confirmation link."""


class PasswordResetConfirmationEmail(djoser_email.PasswordResetConfirmationEmail):
    """Password reset confirmation e-mail."""


class PasswordChangedConfirmationEmail(djoser_email.PasswordChangedConfirmationEmail):
    """Notification sent once a password change has been completed."""


class UsernameChangedConfirmationEmail(djoser_email.UsernameChangedConfirmationEmail):
    """Notification sent after the username has been changed."""


class UsernameResetEmail(djoser_email.UsernameResetEmail):
    """Username reset e-mail containing the reset instructions."""


class UsernameResetConfirmationEmail(djoser_email.UsernameResetConfirmationEmail):
    """Confirmation e-mail sent after a username reset is completed."""


__all__ = [
    'ActivationEmail',
    'ConfirmationEmail',
    'PasswordResetEmail',
    'PasswordResetConfirmationEmail',
    'PasswordChangedConfirmationEmail',
    'UsernameChangedConfirmationEmail',
    'UsernameResetEmail',
    'UsernameResetConfirmationEmail',
]
