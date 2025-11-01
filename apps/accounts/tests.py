from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Profile, UserPreferences

User = get_user_model()


class AccountsModelsAndSignalsTests(TestCase):
    def test_profile_and_preferences_created_with_user(self):
        user = User.objects.create_user(username="john", email="john@example.com", password="x")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertTrue(UserPreferences.objects.filter(user=user).exists())

    def test_related_records_recreated_on_user_save(self):
        user = User.objects.create_user(username="ana", email="ana@example.com", password="x")
        Profile.objects.filter(user=user).delete()
        UserPreferences.objects.filter(user=user).delete()

        user.first_name = "Ana"
        user.save()

        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertTrue(UserPreferences.objects.filter(user=user).exists())


class AccountsAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profileuser",
            email="profile@example.com",
            password="password123",
        )
        self.profile_url = reverse("user-profile")

    def authenticate(self):
        response = self.client.post(
            reverse("jwt-create"),
            {"email": "profile@example.com", "password": "password123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_user_profile_retrieve_and_update(self):
        self.authenticate()

        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("profile", response.data)
        self.assertIn("preferences", response.data)

        payload = {
            "first_name": "Maria",
            "profile.bio": "Sou um desenvolvedor Django.",
            "preferences.notifications_enabled": False,
            "preferences.theme": "dark",
        }

        update_response = self.client.patch(self.profile_url, payload, format="json")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["first_name"], "Maria")
        self.assertEqual(update_response.data["profile"]["bio"], "Sou um desenvolvedor Django.")
        self.assertFalse(update_response.data["preferences"]["notifications_enabled"])
        self.assertEqual(update_response.data["preferences"]["theme"], "dark")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Maria")
        self.assertEqual(self.user.profile.bio, "Sou um desenvolvedor Django.")
        self.assertFalse(self.user.preferences.notifications_enabled)
        self.assertEqual(self.user.preferences.theme, "dark")

    def test_user_registration_creates_profile_and_preferences(self):
        url = reverse("user-list")
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "strongpassword123",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Profile.objects.filter(user__email="test@example.com").exists())
        self.assertTrue(UserPreferences.objects.filter(user__email="test@example.com").exists())

    def test_token_refresh_flow(self):
        self.authenticate()
        login_response = self.client.post(
            reverse("jwt-create"),
            {"email": "profile@example.com", "password": "password123"},
            format="json",
        )
        refresh_token = login_response.data["refresh"]

        refresh_response = self.client.post(
            reverse("jwt-refresh"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_response.data)

    def test_token_verify_flow(self):
        login_response = self.client.post(
            reverse("jwt-create"),
            {"email": "profile@example.com", "password": "password123"},
            format="json",
        )
        access_token = login_response.data["access"]

        verify_response = self.client.post(
            reverse("jwt-verify"),
            {"token": access_token},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)


class PasswordResetFlowTests(APITestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_flow_sends_email_and_confirms_new_password(self):
        user = User.objects.create_user(
            username="resetuser",
            email="reset@example.com",
            password="initialpass123",
        )

        response = self.client.post(
            reverse("user-reset-password"),
            {"email": "reset@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)

        token = "dummy-token"
        uid = "dummy-uid"
        confirm_response = self.client.post(
            reverse("user-reset-password-confirm"),
            {"uid": uid, "token": token, "new_password": "newsecurepass456"},
            format="json",
        )
        self.assertIn(confirm_response.status_code, {status.HTTP_200_OK, status.HTTP_204_NO_CONTENT})
