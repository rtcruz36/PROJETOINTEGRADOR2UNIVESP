"""Serializers for the accounts application."""

from djoser.serializers import (
    SetPasswordSerializer as BaseSetPasswordSerializer,
    UserCreateSerializer as BaseUserCreateSerializer,
    UserSerializer as BaseUserSerializer,
)
from rest_framework import serializers

from .models import Profile, User, UserPreferences


class ProfileSerializer(serializers.ModelSerializer):
    profile_picture = serializers.ImageField(allow_null=True, required=False)

    class Meta:
        model = Profile
        fields = ["profile_picture", "bio"]


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ["notifications_enabled", "theme"]


class UserSerializer(BaseUserSerializer):
    """Extende o serializer padrão do Djoser com os dados do perfil."""

    profile = ProfileSerializer(read_only=True)
    preferences = UserPreferencesSerializer(read_only=True)

    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "profile",
            "preferences",
        ]


class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ["id", "email", "username", "password", "first_name", "last_name"]


class SetPasswordSerializer(BaseSetPasswordSerializer):
    """Serializador customizado para alterar a senha do usuário autenticado."""

    pass


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer completo usado para leitura e atualização do perfil."""

    profile = ProfileSerializer(required=False)
    preferences = UserPreferencesSerializer(required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "profile",
            "preferences",
        ]
        extra_kwargs = {
            "email": {"required": False},
            "username": {"read_only": True},
        }

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        preferences_data = validated_data.pop("preferences", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if profile_data is not None:
            profile = getattr(instance, "profile", None)
            if profile is None:
                profile = Profile.objects.create(user=instance)
            picture = profile_data.get("profile_picture", serializers.empty)
            if picture is not serializers.empty:
                if picture in (None, ""):
                    if profile.profile_picture:
                        profile.profile_picture.delete(save=False)
                    profile.profile_picture = None
                else:
                    profile.profile_picture = picture
            if "bio" in profile_data:
                profile.bio = profile_data["bio"]
            profile.save()

        if preferences_data is not None:
            preferences = getattr(instance, "preferences", None)
            if preferences is None:
                preferences = UserPreferences.objects.create(user=instance)
            for field, value in preferences_data.items():
                setattr(preferences, field, value)
            preferences.save()

        return instance
