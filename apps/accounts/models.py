from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class User(AbstractUser):
    """Modelo de usuário principal do sistema."""

    email = models.EmailField(unique=True, verbose_name="Endereço de e-mail")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self) -> str:  # pragma: no cover - representação simples
        return self.email


class Profile(models.Model):
    """Informações adicionais do usuário."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Usuário",
    )
    profile_picture = models.ImageField(
        upload_to="profile_pics/",
        null=True,
        blank=True,
        verbose_name="Foto de Perfil",
    )
    bio = models.TextField(max_length=500, blank=True, verbose_name="Biografia")

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"

    def __str__(self) -> str:  # pragma: no cover - representação simples
        return f"Perfil de {self.user.username}"


class UserPreferences(models.Model):
    """Preferências persistentes do usuário."""

    class Theme(models.TextChoices):
        SYSTEM = "system", "Padrão do sistema"
        LIGHT = "light", "Claro"
        DARK = "dark", "Escuro"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
        verbose_name="Usuário",
    )
    notifications_enabled = models.BooleanField(default=True)
    theme = models.CharField(
        max_length=16,
        choices=Theme.choices,
        default=Theme.SYSTEM,
    )

    class Meta:
        verbose_name = "Preferências do usuário"
        verbose_name_plural = "Preferências dos usuários"

    def __str__(self) -> str:  # pragma: no cover - representação simples
        return f"Preferências de {self.user.username}"


@receiver(post_save, sender=User, weak=False)
def ensure_related_records(sender, instance, created, **kwargs):
    """Garante a criação de perfil e preferências para todo usuário."""

    if created:
        Profile.objects.create(user=instance)
        UserPreferences.objects.create(user=instance)
        return

    try:
        instance.profile
    except ObjectDoesNotExist:
        Profile.objects.get_or_create(user=instance)

    try:
        instance.preferences
    except ObjectDoesNotExist:
        UserPreferences.objects.get_or_create(user=instance)
