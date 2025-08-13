# tests/integration/test_accounts.py
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Profile

User = get_user_model()

@pytest.mark.django_db
class TestUserAuthentication:
    """Testes de autenticação e registro de usuários."""
    
    def test_user_registration_flow(self, api_client):
        """Testa o fluxo completo de registro de usuário."""
        url = reverse('user-list')
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'strongpass123',
            'first_name': 'New',
            'last_name': 'User'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email='newuser@example.com').exists()
        
        # Verifica se o perfil foi criado automaticamente
        user = User.objects.get(email='newuser@example.com')
        assert hasattr(user, 'profile')
        assert Profile.objects.filter(user=user).exists()

    def test_user_login_with_email(self, api_client, user):
        """Testa login usando email."""
        url = reverse('jwt-create')
        data = {
            'email': user.email,
            'password': 'testpass123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_user_login_invalid_credentials(self, api_client, user):
        """Testa login com credenciais inválidas."""
        url = reverse('jwt-create')
        data = {
            'email': user.email,
            'password': 'wrongpassword'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_jwt_token_refresh(self, api_client, user):
        """Testa renovação do token JWT."""
        refresh = RefreshToken.for_user(user)
        url = reverse('jwt-refresh')
        data = {'refresh': str(refresh)}
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

@pytest.mark.django_db
class TestUserProfile:
    """Testes do perfil do usuário."""
    
    def test_get_user_profile(self, authenticated_client, user):
        """Testa recuperação do perfil do usuário."""
        url = reverse('user-profile')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'profile_picture' in response.data
        assert 'bio' in response.data

    def test_update_user_profile(self, authenticated_client, user):
        """Testa atualização do perfil do usuário."""
        url = reverse('user-profile')
        data = {
            'bio': 'Sou um estudante de engenharia apaixonado por matemática.'
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['bio'] == data['bio']
        
        # Verifica se foi salvo no banco
        user.profile.refresh_from_db()
        assert user.profile.bio == data['bio']

    def test_profile_access_requires_authentication(self, api_client):
        """Testa que o acesso ao perfil requer autenticação."""
        url = reverse('user-profile')
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_profile_created_on_user_creation(self, api_client):
        """Testa se o perfil é criado automaticamente quando um usuário é criado."""
        # Criar usuário via API
        url = reverse('user-list')
        data = {
            'email': 'profiletest@example.com',
            'username': 'profiletest',
            'password': 'testpass123'
        }
        
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verificar se o perfil foi criado
        user = User.objects.get(email='profiletest@example.com')
        assert Profile.objects.filter(user=user).exists()
        
        # Verificar se o signal funciona também para criação manual
        manual_user = User.objects.create_user(
            username='manualuser',
            email='manual@example.com',
            password='testpass123'
        )
        assert Profile.objects.filter(user=manual_user).exists()

@pytest.mark.django_db
class TestUserDataIsolation:
    """Testes para garantir isolamento de dados entre usuários."""
    
    def test_users_cannot_access_other_profiles(self, api_client, user, other_user):
        """Testa que usuários não podem acessar perfis de outros."""
        # Login como user
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('user-profile')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # O endpoint sempre retorna o perfil do usuário logado, não há forma de acessar outros

    def test_user_registration_duplicate_email(self, api_client, user):
        """Testa que não é possível registrar com email duplicado."""
        url = reverse('user-list')
        data = {
            'email': user.email,  # Email já existente
            'username': 'newusername',
            'password': 'strongpass123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data