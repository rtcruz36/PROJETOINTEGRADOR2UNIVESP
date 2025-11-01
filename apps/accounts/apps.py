from django.apps import AppConfig
from django.conf import settings
from pathlib import Path


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        """Garante a existência do diretório de fotos de perfil."""
        media_root = Path(settings.MEDIA_ROOT)
        profile_pics_dir = media_root / 'profile_pics'
        profile_pics_dir.mkdir(parents=True, exist_ok=True)
