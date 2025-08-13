# apps/accounts/urls.py

from django.urls import path, include
from .views import UserProfileAPIView

urlpatterns = [
    # URLs geradas pelo Djoser para autenticação (login, logout, etc.)
    # Ex: /api/auth/jwt/create/ (login), /api/auth/users/ (registro)
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),

    # Nossa URL customizada para o perfil do usuário
    path('profile/', UserProfileAPIView.as_view(), name='user-profile'),
]
