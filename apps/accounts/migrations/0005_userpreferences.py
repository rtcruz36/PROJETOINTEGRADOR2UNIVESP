# Generated manually for user preferences model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_preferences(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    UserPreferences = apps.get_model("accounts", "UserPreferences")
    for user in User.objects.all():
        UserPreferences.objects.get_or_create(user=user)


def noop(apps, schema_editor):
    """Reverse operation placeholder."""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_profile"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPreferences",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notifications_enabled", models.BooleanField(default=True)),
                (
                    "theme",
                    models.CharField(
                        choices=[("system", "Padrão do sistema"), ("light", "Claro"), ("dark", "Escuro")],
                        default="system",
                        max_length=16,
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="preferences",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuário",
                    ),
                ),
            ],
            options={
                "verbose_name": "Preferências do usuário",
                "verbose_name_plural": "Preferências dos usuários",
            },
        ),
        migrations.RunPython(create_preferences, noop),
    ]
