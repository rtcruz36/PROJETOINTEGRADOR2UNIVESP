# apps/accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile

# Crie uma classe para customizar como o Profile aparece junto com o User
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Perfis'

# Estenda a classe UserAdmin padrão para incluir o Profile
class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)

# Registre seus modelos
admin.site.register(User, CustomUserAdmin)
# Não precisamos registrar o Profile separadamente, pois ele já está "inline" com o User.
