# tests/integration/test_scheduling.py
import pytest
from django.urls import reverse
from rest_framework import status
from datetime import date, timedelta
from unittest.mock import patch

from apps.scheduling.models import StudyPlan, StudyLog

@pytest.mark.django_db
class TestStudyPlanViewSet:
    """Testes do ViewSet de Planos de Estudo."""
    
    def test_create_study_plan(self, authenticated_client, course):
        """Testa criação de plano de estudo."""
        url = reverse('studyplan-list')
        data = {
            'course': course.id,
            'day_of_week': 0,  # Segunda-feira
            'minutes_planned': 90
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['course'] == course.id
        assert response.data['day_of_week'] == 0
        assert response.data['minutes_planned'] == 90
        assert response.data['day_of_week_display'] == 'Segunda-feira'
        
        # Verifica se foi salvo no banco
        assert StudyPlan.objects.filter(course=course, day_of_week=0).exists()

    def test_list_study_plans(self, authenticated_client, study_plan):
        """Testa listagem de planos de estudo."""
        url = reverse('studyplan-list')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['course_title'] == study_plan.course.title

    def test_list_study_plans_filtered_by_course(self, authenticated_client, user):
        """Testa filtro de planos por disciplina."""
        from apps.learning.models import Course
        
        course1 = Course.objects.create(user=user, title='Curso 1')
        course2 = Course.objects.create(user=user, title='Curso 2')
        
        StudyPlan.objects.create(user=user, course=course1, day_of_week=0, minutes_planned=60)
        StudyPlan.objects.create(user=user, course=course2, day_of_week=1, minutes_planned=45)
        
        url = reverse('studyplan-list')
        response = authenticated_client.get(url, {'course_id': course1.id})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['course'] == course1.id

    def test_update_study_plan(self, authenticated_client, study_plan):
        """Testa atualização de plano de estudo."""
        url = reverse('studyplan-detail', args=[study_plan.id])
        data = {
            'minutes_planned': 120
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['minutes_planned'] == 120
        
        # Verifica no banco
        study_plan.refresh_from_db()
        assert study_plan.minutes_planned == 120

    def test_delete_study_plan(self, authenticated_client, study_plan):
        """Testa exclusão de plano de estudo."""
        url = reverse('studyplan-detail', args=[study_plan.id])
        
        response = authenticated_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not StudyPlan.objects.filter(id=study_plan.id).exists()

    def test_unique_constraint_study_plan(self, authenticated_client, study_plan):
        """Testa que não é possível criar planos duplicados."""
        url = reverse('studyplan-list')
        data = {
            'course': study_plan.course.id,
            'day_of_week': study_plan.day_of_week,  # Mesmo dia
            'minutes_planned': 45
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_study_plan_validation_other_user_course(self, authenticated_client, other_user):
        """Testa que não é possível criar plano para curso de outro usuário."""
        from apps.learning.models import Course
        
        other_course = Course.objects.create(user=other_user, title='Curso do Outro')
        
        url = reverse('studyplan-list')
        data = {
            'course': other_course.id,
            'day_of_week': 0,
            'minutes_planned': 60
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestStudyLogViewSet:
    """Testes do ViewSet de Registros de Estudo."""
    
    def test_create_study_log(self, authenticated_client, course, topic):
        """Testa criação de registro de estudo."""
        url = reverse('studylog-list')
        data = {
            'course': course.id,
            'topic': topic.id,
            'date': date.today().isoformat(),
            'minutes_studied': 45,
            'notes': 'Estudei conceitos básicos de derivadas'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['course'] == course.id
        assert response.data['topic'] == topic.id
        assert response.data['minutes_studied'] == 45
        
        # Verifica se foi salvo no banco
        assert StudyLog.objects.filter(course=course, topic=topic).exists()

    def test_create_study_log_without_topic(self, authenticated_client, course):
        """Testa criação de registro de estudo sem tópico específico."""
        url = reverse('studylog-list')
        data = {
            'course': course.id,
            'date': date.today().isoformat(),
            'minutes_studied': 30,
            'notes': 'Estudo geral da disciplina'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['topic'] is None

    def test_list_study_logs(self, authenticated_client, study_log):
        """Testa listagem de registros de estudo."""
        url = reverse('studylog-list')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['minutes_studied'] == study_log.minutes_studied

    def test_update_study_log(self, authenticated_client, study_log):
        """Testa atualização de registro de estudo."""
        url = reverse('studylog-detail', args=[study_log.id])
        data = {
            'minutes_studied': 60,
            'notes': 'Notas atualizadas'
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['minutes_studied'] == 60
        assert response.data['notes'] == 'Notas atualizadas'

    def test_study_log_validation_other_user_course(self, authenticated_client, other_user):
        """Testa que não é possível criar log para curso de outro usuário."""
        from apps.learning.models import Course
        
        other_course = Course.objects.create(user=other_user, title='Curso do Outro')
        
        url = reverse('studylog-list')
        data = {
            'course': other_course.id,
            'date': date.today().isoformat(),
            'minutes_studied': 30
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestGenerateSchedule:
    """Testes de geração de cronograma."""
    
    def test_generate_schedule_success(self, authenticated_client, topic, subtopics, study_plan):
        """Testa geração bem-sucedida de cronograma."""
        # Mock da resposta da IA
        mock_schedule = {
            'Segunda-feira': [
                {
                    'subtopic': 'Conceito de Derivada',
                    'estimated_time': 30,
                    'difficulty': 'Fácil'
                },
                {
                    'subtopic': 'Regras de Derivação',
                    'estimated_time': 30,
                    'difficulty': 'Médio'
                }
            ],
            'Terça-feira': [],
            'Quarta-feira': [],
            'Quinta-feira': [],
            'Sexta-feira': [],
            'Sábado': [],
            'Domingo': []
        }
        
        with patch('apps.core.services.deepseek_service.distribuir_subtopicos_no_cronograma') as mock:
            mock.return_value = mock_schedule
            
            url = reverse('generate-schedule')
            data = {'topic_id': topic.id}
            
            response = authenticated_client.post(url, data, format='json')
            
            assert response.status_code == status.HTTP_200_OK
            assert 'Segunda-feira' in response.data
            assert len(response.data['Segunda-feira']) == 2

    def test_generate_schedule_no_subtopics(self, authenticated_client, topic, study_plan):
        """Testa geração de cronograma para tópico sem subtópicos."""
        # Garantir que não há subtópicos
        topic.subtopics.all().delete()
        
        url = reverse('generate-schedule')
        data = {'topic_id': topic.id}
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'subtópicos' in response.data['error']

    def test_generate_schedule_no_study_plans(self, authenticated_client, topic, subtopics):
        """Testa geração de cronograma sem planos de estudo definidos."""
        url = reverse('generate-schedule')
        data = {'topic_id': topic.id}
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'plano de estudo' in response.data['error']

    def test_generate_schedule_invalid_topic(self, authenticated_client):
        """Testa geração de cronograma para tópico inexistente."""
        url = reverse('generate-schedule')
        data = {'topic_id': 99999}
        
        response = authenticated_client.get(url, data, format='json')
        
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED  # GET não permitido

    def test_generate_schedule_other_user_topic(self, api_client, other_user, topic, subtopics):
        """Testa que usuário não pode gerar cronograma para tópico de outro."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('generate-schedule')
        data = {'topic_id': topic.id}
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_generate_schedule_ai_failure(self, authenticated_client, topic, subtopics, study_plan):
        """Testa comportamento quando a IA falha."""
        with patch('apps.core.services.deepseek_service.distribuir_subtopicos_no_cronograma') as mock:
            mock.return_value = {}  # IA retorna cronograma vazio
            
            url = reverse('generate-schedule')
            data = {'topic_id': topic.id}
            
            response = authenticated_client.post(url, data, format='json')
            
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_generate_schedule_missing_topic_id(self, authenticated_client):
        """Testa geração sem fornecer topic_id."""
        url = reverse('generate-schedule')
        data = {}
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'topic_id' in response.data['error']

@pytest.mark.django_db
class TestSchedulingCompleteFlow:
    """Testes do fluxo completo de agendamento."""
    
    def test_complete_scheduling_flow(self, authenticated_client, user, mock_deepseek_subtopicos, mock_deepseek_plano):
        """Testa fluxo completo: criar curso -> definir planos -> gerar cronograma."""
        # 1. Criar curso e tópico
        create_url = reverse('create-study-plan')
        create_data = {
            'course_title': 'Álgebra Linear',
            'topic_title': 'Matrizes'
        }
        
        create_response = authenticated_client.post(create_url, create_data, format='json')
        assert create_response.status_code == status.HTTP_201_CREATED
        
        topic_id = create_response.data['id']
        course_id = create_response.data['course']
        
        # 2. Definir planos de estudo para a semana
        plan_url = reverse('studyplan-list')
        for day in range(5):  # Segunda a sexta
            plan_data = {
                'course': course_id,
                'day_of_week': day,
                'minutes_planned': 60
            }
            plan_response = authenticated_client.post(plan_url, plan_data, format='json')
            assert plan_response.status_code == status.HTTP_201_CREATED
        
        # 3. Gerar cronograma
        mock_schedule = {
            'Segunda-feira': [{'subtopic': 'Sub1', 'estimated_time': 60, 'difficulty': 'Fácil'}],
            'Terça-feira': [{'subtopic': 'Sub2', 'estimated_time': 60, 'difficulty': 'Médio'}],
            'Quarta-feira': [{'subtopic': 'Sub3', 'estimated_time': 60, 'difficulty': 'Médio'}],
            'Quinta-feira': [{'subtopic': 'Sub4', 'estimated_time': 60, 'difficulty': 'Difícil'}],
            'Sexta-feira': [],
            'Sábado': [],
            'Domingo': []
        }
        
        with patch('apps.core.services.deepseek_service.distribuir_subtopicos_no_cronograma') as mock:
            mock.return_value = mock_schedule
            
            schedule_url = reverse('generate-schedule')
            schedule_data = {'topic_id': topic_id}
            
            schedule_response = authenticated_client.post(schedule_url, schedule_data, format='json')
            assert schedule_response.status_code == status.HTTP_200_OK
            assert len([day for day, tasks in schedule_response.data.items() if tasks]) == 4

    def test_study_tracking_flow(self, authenticated_client, course, topic):
        """Testa fluxo de acompanhamento de estudos."""
        # 1. Registrar várias sessões de estudo
        log_url = reverse('studylog-list')
        
        study_sessions = [
            {'date': date.today() - timedelta(days=2), 'minutes': 45},
            {'date': date.today() - timedelta(days=1), 'minutes': 60},
            {'date': date.today(), 'minutes': 30}
        ]
        
        for session in study_sessions:
            log_data = {
                'course': course.id,
                'topic': topic.id,
                'date': session['date'].isoformat(),
                'minutes_studied': session['minutes'],
                'notes': f'Sessão de {session["minutes"]} minutos'
            }
            
            response = authenticated_client.post(log_url, log_data, format='json')
            assert response.status_code == status.HTTP_201_CREATED
        
        # 2. Verificar histórico
        list_response = authenticated_client.get(log_url)
        assert list_response.status_code == status.HTTP_200_OK
        assert len(list_response.data) == 3
        
        # Verificar ordenação (mais recentes primeiro)
        dates = [log['date'] for log in list_response.data]
        assert dates == sorted(dates, reverse=True)