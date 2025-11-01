# apps/accounts/tests.py

import re

from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.accounts.models import User, Profile
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model



User = get_user_model()

class AccountsModelsAndSignalsTests(TestCase):
    def test_user_str_returns_email(self):
        u = User.objects.create_user(username="john", email="john@example.com", password="x")
        self.assertEqual(str(u), "john@example.com")  # cobre User.__str__

    def test_profile_str_uses_username(self):
        u = User.objects.create_user(username="ana", email="ana@example.com", password="x")
        # sinal deve ter criado o profile
        p = Profile.objects.get(user=u)
        self.assertIn("Perfil de ana", str(p))  # cobre Profile.__str__

    def test_signal_recreates_profile_when_missing_on_update(self):
    
    #Cobre o ramo do sinal post_save com created=False e sem atributo 'profile':#
   # - cria usuário (created=True -> já cobre a criação)#
    #- apaga o Profile#
   # - salva o usuário de novo (created=False), o sinal deve recriar o Profile

    # Cria um usuário, o que gera automaticamente um perfil via sinal
        u = User.objects.create_user(username="maria", email="maria@example.com", password="x")
        self.assertTrue(Profile.objects.filter(user=u).exists())

    # Remover o profile para simular estado inconsistente
        try:
        # Exclui o perfil diretamente usando o objeto Profile
            profile = Profile.objects.get(user=u)
            profile.delete()
        except Profile.DoesNotExist:
            pass  # Se o perfil não existir, não faz nada

    # Verifica se o perfil foi excluído corretamente
        self.assertFalse(Profile.objects.filter(user=u).exists())

    # Salvar o usuário novamente (created=False)
        u.first_name = 'Maria'
        u.save()

    # Verificar se o perfil foi recriado
        self.assertTrue(Profile.objects.filter(user=u).exists())
        
        
class AccountsAPITests(APITestCase):


    def test_set_password_with_valid_token(self):
        """Garante que um usuário autenticado pode alterar a própria senha."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        User = User.objects.create_user(
            username='changepass',
            email='changepass@example.com',
            password='old_password123',
        )

        login_url = reverse('jwt-create')
        login_data = {"email": "changepass@example.com", "password": "old_password123"}
        login_response = self.client.post(login_url, login_data, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        token = login_response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        url = reverse('user-set-password')
        data = {
            'current_password': 'old_password123',
            'new_password': 'new_secure_password456',
        }

        # Se sua view espera POST/PATCH em vez de PUT, mude a linha abaixo para .post(...) ou .patch(...)
        response = self.client.put(url, data, format='json')

        # Se sua view retorna 200 em vez de 204, ajuste a asserção abaixo.
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        User.refresh_from_db()
        self.assertTrue(User.check_password('new_secure_password456'))


    def test_user_registration(self):
        """
        Garante que um novo usuário pode ser registrado com sucesso.
        """
        url = reverse('user-list') # Djoser nomeia a URL de registro como 'user-list'
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "strongpassword123"
        }
        
        # Ação: Faz a requisição POST para registrar
        response = self.client.post(url, data, format='json')
        
        # Verificação
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().email, 'test@example.com')
        # Verifica se o sinal criou o perfil automaticamente
        self.assertTrue(Profile.objects.filter(user__email='test@example.com').exists())

    def test_user_login_and_profile_access(self):
        """
        Garante que um usuário pode fazer login e acessar seu perfil.
        """
        # Preparação: Cria um usuário primeiro
        user = User.objects.create_user(username='profileuser', email='profile@example.com', password='password')
        
        # Ação 1: Fazer login para obter o token JWT
        login_url = reverse('jwt-create') # URL do Simple JWT via Djoser
        login_data = {"email": "profile@example.com", "password": "password"}
        login_response = self.client.post(login_url, login_data, format='json')
        
        # Verificação 1: Login bem-sucedido
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_response.data)
        
        # Ação 2: Usar o token para acessar o endpoint do perfil
        token = login_response.data['access']
        profile_url = reverse('user-profile')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}') # Autentica o cliente
        profile_response = self.client.get(profile_url)
        
        # Verificação 2: Acesso ao perfil bem-sucedido
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_response.data['bio'], '') # Bio inicial está vazia

        # Ação 3: Atualizar o perfil
        update_data = {"bio": "Sou um desenvolvedor Django."}
        update_response = self.client.patch(profile_url, update_data, format='json')

        # Verificação 3: Atualização bem-sucedida
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data['bio'], "Sou um desenvolvedor Django.")
        user.profile.refresh_from_db() # Recarrega o perfil do banco
        self.assertEqual(user.profile.bio, "Sou um desenvolvedor Django.")

    def test_jwt_refresh_endpoint_returns_new_access_token(self):
        user = User.objects.create_user(username='refreshuser', email='refresh@example.com', password='password')

        login_response = self.client.post(
            reverse('jwt-create'),
            {"email": "refresh@example.com", "password": "password"},
            format='json',
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        refresh_token = login_response.data['refresh']
        original_access = login_response.data['access']

        refresh_response = self.client.post(
            reverse('jwt-refresh'),
            {"refresh": refresh_token},
            format='json',
        )

        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_response.data)
        self.assertNotEqual(original_access, refresh_response.data['access'])

    def test_jwt_verify_endpoint_accepts_valid_token(self):
        User.objects.create_user(username='verifyuser', email='verify@example.com', password='password')

        login_response = self.client.post(
            reverse('jwt-create'),
            {"email": "verify@example.com", "password": "password"},
            format='json',
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        access_token = login_response.data['access']

        verify_response = self.client.post(
            reverse('jwt-verify'),
            {"token": access_token},
            format='json',
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data, {})


class PasswordResetFlowTests(APITestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_flow_sends_email_and_confirms_new_password(self):
        user = User.objects.create_user(
            username='resetuser',
            email='reset@example.com',
            password='initialPassword123',
        )

        response = self.client.post(
            '/api/accounts/auth/users/reset_password/',
            {'email': user.email},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)

        email_body = mail.outbox[0].body
        match = re.search(
            r'#/password/reset/confirm/(?P<uid>[^/]+)/(?P<token>[^\s/]+)',
            email_body,
        )
        self.assertIsNotNone(match, 'Password reset e-mail should contain uid and token')

        confirm_response = self.client.post(
            '/api/accounts/auth/users/reset_password_confirm/',
            {
                'uid': match.group('uid'),
                'token': match.group('token'),
                'new_password': 'NewPassword456!',
                're_new_password': 'NewPassword456!',
            },
            format='json',
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_204_NO_CONTENT)

        login_response = self.client.post(
            reverse('jwt-create'),
            {'email': user.email, 'password': 'NewPassword456!'},
            format='json',
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_response.data)
