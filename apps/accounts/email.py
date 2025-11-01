"""Custom Djoser e-mail classes for the accounts app."""

from djoser import email as djoser_email


class ActivationEmail(djoser_email.ActivationEmail):
    """Activation e-mail using the project's default configuration."""


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
