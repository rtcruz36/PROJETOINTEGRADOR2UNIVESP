# apps/accounts/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.accounts.models import User, Profile

class AccountsAPITests(APITestCase):

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
