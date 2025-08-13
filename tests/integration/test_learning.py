# tests/integration/test_learning.py
import pytest
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch

from apps.learning.models import Course, Topic, Subtopic

@pytest.mark.django_db
class TestLearningCreationFlow:
    """Testes do fluxo principal de criação de planos de estudo."""
    
    def test_create_study_plan_complete_flow(self, authenticated_client, mock_deepseek_subtopicos, mock_deepseek_plano):
        """Testa o fluxo completo de criação de plano de estudo."""
        url = reverse('create-study-plan')
        data = {
            'course_title': 'Cálculo I',
            'topic_title': 'Limites',
            'course_description': 'Disciplina introdutória de Cálculo'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        assert response.data['title'] == 'Limites'
        assert 'subtopics' in response.data
        assert len(response.data['subtopics']) == 4  # Mock retorna 4 subtópicos
        
        # Verifica se foi criado no banco
        assert Course.objects.filter(title='Cálculo I').exists()
        assert Topic.objects.filter(title='Limites').exists()
        assert Subtopic.objects.count() == 4

    def test_create_study_plan_existing_course(self, authenticated_client, course, mock_deepseek_subtopicos, mock_deepseek_plano):
        """Testa criação de tópico em curso existente."""
        url = reverse('create-study-plan')
        data = {
            'course_title': course.title,  # Curso já existe
            'topic_title': 'Integrais',
            'course_description': 'Nova descrição'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == 'Integrais'
        
        # Verifica que não criou novo curso
        assert Course.objects.filter(title=course.title).count() == 1
        # Verifica que criou novo tópico no curso existente
        assert Topic.objects.filter(course=course, title='Integrais').exists()

    def test_create_study_plan_case_insensitive(self, authenticated_client, course, mock_deepseek_subtopicos, mock_deepseek_plano):
        """Testa que a criação é case-insensitive."""
        url = reverse('create-study-plan')
        data = {
            'course_title': course.title.upper(),  # Maiúsculo
            'topic_title': 'LIMITES',  # Maiúsculo
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        # Não deve criar novo curso
        assert Course.objects.filter(title__iexact=course.title).count() == 1

    def test_create_study_plan_ia_failure_graceful(self, authenticated_client):
        """Testa que o sistema funciona mesmo se a IA falhar."""
        with patch('apps.core.services.deepseek_service.sugerir_subtopicos') as mock_subtopicos, \
             patch('apps.core.services.deepseek_service.sugerir_plano_de_topico') as mock_plano:
            
            # Simula falha na IA
            mock_subtopicos.return_value = []
            mock_plano.return_value = ""
            
            url = reverse('create-study-plan')
            data = {
                'course_title': 'Física I',
                'topic_title': 'Cinemática',
            }
            
            response = authenticated_client.post(url, data, format='json')
            
            # Deve continuar funcionando mesmo sem dados da IA
            assert response.status_code == status.HTTP_201_CREATED
            assert Course.objects.filter(title='Física I').exists()
            assert Topic.objects.filter(title='Cinemática').exists()
            # Sem subtópicos criados devido à falha da IA
            assert response.data['subtopics'] == []

    def test_create_study_plan_requires_authentication(self, api_client):
        """Testa que criação requer autenticação."""
        url = reverse('create-study-plan')
        data = {
            'course_title': 'Teste',
            'topic_title': 'Teste',
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
class TestCourseViewSet:
    """Testes do ViewSet de Cursos."""
    
    def test_list_user_courses(self, authenticated_client, course):
        """Testa listagem de cursos do usuário."""
        url = reverse('course-list')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['title'] == course.title
        assert 'topics' in response.data[0]

    def test_course_detail(self, authenticated_client, course, topic):
        """Testa detalhes de um curso específico."""
        url = reverse('course-detail', args=[course.id])
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['title'] == course.title
        assert len(response.data['topics']) == 1
        assert response.data['topics'][0]['title'] == topic.title

    def test_user_can_only_see_own_courses(self, authenticated_client, other_user):
        """Testa que usuários só veem seus próprios cursos."""
        # Criar curso para outro usuário
        other_course = Course.objects.create(
            user=other_user,
            title='Curso do Outro Usuário'
        )
        
        url = reverse('course-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0  # Não deve ver o curso do outro usuário

@pytest.mark.django_db
class TestTopicViewSet:
    """Testes do ViewSet de Tópicos."""
    
    def test_list_user_topics(self, authenticated_client, topic, subtopics):
        """Testa listagem de tópicos do usuário."""
        url = reverse('topic-list')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['title'] == topic.title
        assert len(response.data[0]['subtopics']) == len(subtopics)

    def test_topic_detail(self, authenticated_client, topic, subtopics):
        """Testa detalhes de um tópico específico."""
        url = reverse('topic-detail', args=[topic.id])
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['title'] == topic.title
        assert response.data['suggested_study_plan'] == topic.suggested_study_plan
        assert len(response.data['subtopics']) == len(subtopics)

@pytest.mark.django_db
class TestSubtopicUpdate:
    """Testes de atualização de subtópicos."""
    
    def test_mark_subtopic_completed(self, authenticated_client, subtopics):
        """Testa marcar subtópico como concluído."""
        subtopic = subtopics[0]
        url = reverse('subtopic-update', args=[subtopic.id])
        data = {'is_completed': True}
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_completed'] is True
        
        # Verifica no banco
        subtopic.refresh_from_db()
        assert subtopic.is_completed is True

    def test_update_subtopic_details(self, authenticated_client, subtopics):
        """Testa atualização dos detalhes do subtópico."""
        subtopic = subtopics[0]
        url = reverse('subtopic-update', args=[subtopic.id])
        data = {
            'details': 'Novos detalhes sobre o conceito de derivada',
            'order': 5
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['details'] == data['details']
        assert response.data['order'] == data['order']

    def test_user_cannot_update_others_subtopics(self, api_client, other_user, subtopics):
        """Testa que usuário não pode atualizar subtópicos de outros."""
        # Login como outro usuário
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        subtopic = subtopics[0]
        url = reverse('subtopic-update', args=[subtopic.id])
        data = {'is_completed': True}
        
        response = api_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.django_db
class TestLearningDataValidation:
    """Testes de validação de dados do módulo learning."""
    
    def test_create_study_plan_missing_fields(self, authenticated_client):
        """Testa criação com campos obrigatórios ausentes."""
        url = reverse('create-study-plan')
        data = {
            'course_title': 'Apenas título do curso'
            # topic_title ausente
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'topic_title' in response.data

    def test_create_study_plan_empty_strings(self, authenticated_client):
        """Testa criação com strings vazias."""
        url = reverse('create-study-plan')
        data = {
            'course_title': '   ',  # Apenas espaços
            'topic_title': '',  # String vazia
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST