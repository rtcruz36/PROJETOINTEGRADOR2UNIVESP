# apps/accounts/serializers.py

from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers
from .models import Profile, User

class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializador para o perfil do usuário.
    """
    class Meta:
        model = Profile
        fields = ['profile_picture', 'bio']

class UserSerializer(BaseUserSerializer):
    """
    Serializador para exibir os dados do usuário, incluindo o perfil.
    """
    profile = ProfileSerializer(read_only=True)

    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'profile']

class UserCreateSerializer(BaseUserCreateSerializer):
    """
    Serializador para a criação de novos usuários.
    Garante que o campo de e-mail seja usado para o login.
    """
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ['id', 'email', 'username', 'password', 'first_name', 'last_name']
