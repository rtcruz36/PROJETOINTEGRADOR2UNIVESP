# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ObjectDoesNotExist

class User(AbstractUser):
    """
    Modelo de Usuário personalizado. Herda tudo do usuário padrão do Django,
    mas podemos adicionar campos extras aqui se necessário no futuro.
    Por enquanto, apenas o usamos para definir que este é o nosso modelo
    de usuário principal no projeto.
    """
    email = models.EmailField(unique=True, verbose_name="Endereço de e-mail")

    # Podemos adicionar outros campos diretamente aqui, como:
    # date_of_birth = models.DateField(null=True, blank=True)

    # Dizemos ao Django que o campo de login agora será o 'email'.
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username'] # 'username' ainda é necessário para o admin e outros sistemas.

    def __str__(self):
        return self.email

class Profile(models.Model):
    """
    Modelo de Perfil do Usuário. Armazena informações adicionais
    que não estão relacionadas à autenticação.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name="Usuário"
    )
    # Exemplo de campo: foto de perfil.
    # O 'upload_to' define a subpasta dentro do seu diretório de media.
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        null=True,
        blank=True,
        verbose_name="Foto de Perfil"
    )
    bio = models.TextField(
        max_length=500,
        blank=True,
        verbose_name="Biografia"
    )
    # Podemos adicionar outras informações, como links para redes sociais, etc.
    # linkedin_url = models.URLField(blank=True)
    # github_url = models.URLField(blank=True)

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"

    def __str__(self):
        return f"Perfil de {self.user.username}"

# --- Sinais para automação ---

@receiver(post_save, sender=User, weak=False)
def ensure_profile_on_save(sender, instance, created, **kwargs):
    """
    Garante que sempre exista um Profile vinculado ao User.
    - No create: cria.
    - No update: se não existir no BANCO, cria.
    """
    if created:
        Profile.objects.create(user=instance)
        return

    # checa no banco para evitar cache do reverso OneToOne
    if not Profile.objects.filter(user=instance).exists():
        Profile.objects.create(user=instance)
    else:
        # nada a fazer
        pass