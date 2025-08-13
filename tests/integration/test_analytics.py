# tests/integration/test_analytics.py
import pytest
from django.urls import reverse
from rest_framework import status
from datetime import date, timedelta

from apps.scheduling.models import StudyLog
from apps.assessment.models import Quiz, Question, Attempt, Answer

@pytest.mark.django_db
class TestStudyEffectivenessAnalytics:
    """Testes de análise de eficácia do estudo."""
    
    def test_study_effectiveness_with_data(self, authenticated_client, user, course, topic):
        """Testa análise com dados suficientes para correlação."""
        # Criar outro tópico para ter mais dados
        from apps.learning.models import Topic
        topic2 = Topic.objects.create(
            course=course,
            title='Integrais',
            order=2
        )
        
        # Criar logs de estudo para ambos os tópicos
        StudyLog.objects.create(
            user=user, topic=topic, course=course,
            date=date.today(), minutes_studied=120
        )
        StudyLog.objects.create(
            user=user, topic=topic2, course=course,
            date=date.today(), minutes_studied=60
        )
        
        # Criar quizzes e tentativas
        quiz1 = Quiz.objects.create(topic=topic, title='Quiz Derivadas', total_questions=2)
        quiz2 = Quiz.objects.create(topic=topic2, title='Quiz Integrais', total_questions=2)
        
        # Criar perguntas
        q1 = Question.objects.create(
            quiz=quiz1, question_text='Pergunta 1',
            choices={'A': '1', 'B': '2'}, correct_answer='A'
        )
        q2 = Question.objects.create(
            quiz=quiz2, question_text='Pergunta 2',
            choices={'A': '1', 'B': '2'}, correct_answer='A'
        )
        
        # Criar tentativas com scores diferentes
        attempt1 = Attempt.objects.create(
            user=user, quiz=quiz1, score=90.0,
            correct_answers_count=1, incorrect_answers_count=0
        )
        attempt2 = Attempt.objects.create(
            user=user, quiz=quiz2, score=70.0,
            correct_answers_count=1, incorrect_answers_count=1
        )
        
        url = reverse('analytics-study-effectiveness')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'correlation_coefficient' in response.data
        assert 'interpretation' in response.data
        assert response.data['data_points'] == 2
        assert len(response.data['topic_data']) == 2
        
        # Verificar dados dos tópicos
        topic_data = {item['topic_title']: item for item in response.data['topic_data']}
        assert 'Derivadas' in topic_data
        assert 'Integrais' in topic_data
        assert topic_data['Derivadas']['total_minutes_studied'] == 120
        assert topic_data['Integrais']['total_minutes_studied'] == 60

    def test_study_effectiveness_insufficient_data(self, authenticated_client, user):
        """Testa análise com dados insuficientes."""
        url = reverse('analytics-study-effectiveness')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['correlation_coefficient'] is None
        assert response.data['data_points'] == 0
        assert 'pelo menos dois tópicos' in response.data['interpretation']

    def test_study_effectiveness_one_topic_only(self, authenticated_client, user, course, topic, quiz, questions):
        """Testa análise com apenas um tópico."""
        # Criar dados para apenas um tópico
        StudyLog.objects.create(
            user=user, topic=topic, course=course,
            date=date.today(), minutes_studied=90
        )
        
        Attempt.objects.create(
            user=user, quiz=quiz, score=85.0,
            correct_answers_count=1, incorrect_answers_count=0
        )
        
        url = reverse('analytics-study-effectiveness')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['correlation_coefficient'] is None
        assert response.data['data_points'] == 1
        assert 'pelo menos dois tópicos' in response.data['interpretation']

    def test_study_effectiveness_multiple_attempts_per_topic(self, authenticated_client, user, course, topic, quiz):
        """Testa análise com múltiplas tentativas por tópico (deve usar média)."""
        # Criar logs de estudo
        StudyLog.objects.create(
            user=user, topic=topic, course=course,
            date=date.today() - timedelta(days=1), minutes_studied=60
        )
        StudyLog.objects.create(
            user=user, topic=topic, course=course,
            date=date.today(), minutes_studied=40
        )
        
        # Criar múltiplas tentativas
        Attempt.objects.create(
            user=user, quiz=quiz, score=70.0,
            correct_answers_count=1, incorrect_answers_count=1
        )
        Attempt.objects.create(
            user=user, quiz=quiz, score=90.0,
            correct_answers_count=2, incorrect_answers_count=0
        )
        
        # Criar segundo tópico para comparação
        from apps.learning.models import Topic
        topic2 = Topic.objects.create(course=course, title='Outro Tópico', order=2)
        
        StudyLog.objects.create(
            user=user, topic=topic2, course=course,
            date=date.today(), minutes_studied=30
        )
        
        quiz2 = Quiz.objects.create(topic=topic2, title='Quiz 2', total_questions=1)
        Attempt.objects.create(
            user=user, quiz=quiz2, score=60.0,
            correct_answers_count=0, incorrect_answers_count=1
        )
        
        url = reverse('analytics-study-effectiveness')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data_points'] == 2
        
        # Verificar que usou totais e médias corretas
        topic_data = {item['topic_title']: item for item in response.data['topic_data']}
        assert topic_data['Derivadas']['total_minutes_studied'] == 100  # 60 + 40
        assert topic_data['Derivadas']['average_quiz_score'] == 80.0  # (70 + 90) / 2
        assert topic_data['Outro Tópico']['total_minutes_studied'] == 30
        assert topic_data['Outro Tópico']['average_quiz_score'] == 60.0

    def test_study_effectiveness_user_isolation(self, api_client, user, other_user, course):
        """Testa que análise só considera dados do usuário logado."""
        from apps.learning.models import Topic, Course
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Criar dados para ambos os usuários
        topic = Topic.objects.create(course=course, title='Tópico Comum', order=1)
        
        # Dados do usuário principal
        StudyLog.objects.create(
            user=user, topic=topic, course=course,
            date=date.today(), minutes_studied=60
        )
        
        # Dados do outro usuário (não devem aparecer na análise)
        other_course = Course.objects.create(user=other_user, title='Curso do Outro')
        other_topic = Topic.objects.create(course=other_course, title='Tópico do Outro', order=1)
        StudyLog.objects.create(
            user=other_user, topic=other_topic, course=other_course,
            date=date.today(), minutes_studied=120
        )
        
        # Login como usuário principal
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('analytics-study-effectiveness')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Deve encontrar dados insuficientes porque os dados do outro usuário não são considerados
        assert response.data['data_points'] == 0  # Só logs de estudo não bastam, precisa de tentativas também

    def test_study_effectiveness_requires_authentication(self, api_client):
        """Testa que análise requer autenticação."""
        url = reverse('analytics-study-effectiveness')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

# tests/integration/test_studychat.py
@pytest.mark.django_db
class TestStudyChat:
    """Testes do chat de estudo com IA."""
    
    def test_chat_simple_question(self, authenticated_client, mock_deepseek_success):
        """Testa pergunta simples no chat."""
        url = reverse('studychat-ask')
        data = {
            'question': 'O que é uma derivada?',
            'history': []
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['role'] == 'assistant'
        assert 'content' in response.data
        assert response.data['content'] == 'Resposta mocada da IA'

    def test_chat_with_context_topic(self, authenticated_client, topic, mock_deepseek_success):
        """Testa pergunta com contexto de tópico."""
        url = reverse('studychat-ask')
        data = {
            'question': 'Como calculo a derivada de x²?',
            'history': [],
            'topic_id': topic.id
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['role'] == 'assistant'

    def test_chat_with_conversation_history(self, authenticated_client, mock_deepseek_success):
        """Testa pergunta com histórico de conversa."""
        url = reverse('studychat-ask')
        data = {
            'question': 'Pode dar um exemplo?',
            'history': [
                {'role': 'user', 'content': 'O que é uma derivada?'},
                {'role': 'assistant', 'content': 'Uma derivada mede a taxa de variação...'}
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['role'] == 'assistant'

    def test_chat_invalid_topic_id(self, authenticated_client):
        """Testa pergunta com topic_id inválido."""
        url = reverse('studychat-ask')
        data = {
            'question': 'Teste',
            'history': [],
            'topic_id': 99999  # ID inexistente
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_other_user_topic(self, api_client, other_user, topic):
        """Testa que usuário não pode usar tópico de outro como contexto."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('studychat-ask')
        data = {
            'question': 'Teste',
            'history': [],
            'topic_id': topic.id
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_missing_question(self, authenticated_client):
        """Testa requisição sem pergunta."""
        url = reverse('studychat-ask')
        data = {
            'history': []
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_invalid_history_format(self, authenticated_client):
        """Testa histórico com formato inválido."""
        url = reverse('studychat-ask')
        data = {
            'question': 'Teste',
            'history': [
                {'role': 'invalid_role', 'content': 'Teste'}  # Role inválido
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_long_question(self, authenticated_client, mock_deepseek_success):
        """Testa pergunta muito longa."""
        long_question = 'x' * 5000  # Pergunta muito longa
        
        url = reverse('studychat-ask')
        data = {
            'question': long_question,
            'history': []
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_requires_authentication(self, api_client):
        """Testa que chat requer autenticação."""
        url = reverse('studychat-ask')
        data = {
            'question': 'Teste',
            'history': []
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_chat_ai_service_failure(self, authenticated_client):
        """Testa comportamento quando serviço de IA falha."""
        with patch('apps.core.services.deepseek_service.responder_pergunta_de_estudo') as mock:
            mock.side_effect = Exception("Falha na IA")
            
            url = reverse('studychat-ask')
            data = {
                'question': 'Teste',
                'history': []
            }
            
            response = authenticated_client.post(url, data, format='json')
            
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert 'error' in response.data

@pytest.mark.django_db
class TestCompleteStudyFlow:
    """Testes do fluxo completo de estudo integrando todos os módulos."""
    
    def test_complete_learning_journey(self, authenticated_client, user, mock_deepseek_subtopicos, 
                                     mock_deepseek_plano, mock_deepseek_quiz, mock_deepseek_success):
        """Testa jornada completa de aprendizado."""
        
        # 1. CRIAR PLANO DE ESTUDO
        create_url = reverse('create-study-plan')
        create_data = {
            'course_title': 'Cálculo I',
            'topic_title': 'Derivadas'
        }
        
        create_response = authenticated_client.post(create_url, create_data, format='json')
        assert create_response.status_code == status.HTTP_201_CREATED
        
        topic_id = create_response.data['id']
        course_id = create_response.data['course']
        
        # 2. DEFINIR CRONOGRAMA SEMANAL
        plan_url = reverse('studyplan-list')
        plan_data = {
            'course': course_id,
            'day_of_week': 0,  # Segunda-feira
            'minutes_planned': 90
        }
        
        plan_response = authenticated_client.post(plan_url, plan_data, format='json')
        assert plan_response.status_code == status.HTTP_201_CREATED
        
        # 3. GERAR CRONOGRAMA DETALHADO
        mock_schedule = {
            'Segunda-feira': [
                {'subtopic': 'Conceito de Limite', 'estimated_time': 45, 'difficulty': 'Fácil'},
                {'subtopic': 'Propriedades dos Limites', 'estimated_time': 45, 'difficulty': 'Médio'}
            ],
            'Terça-feira': [],
            'Quarta-feira': [],
            'Quinta-feira': [],
            'Sexta-feira': [],
            'Sábado': [],
            'Domingo': []
        }
        
        with patch('apps.core.services.deepseek_service.distribuir_subtopicos_no_cronograma') as schedule_mock:
            schedule_mock.return_value = mock_schedule
            
            schedule_url = reverse('generate-schedule')
            schedule_data = {'topic_id': topic_id}
            
            schedule_response = authenticated_client.post(schedule_url, schedule_data, format='json')
            assert schedule_response.status_code == status.HTTP_200_OK
        
        # 4. REGISTRAR SESSÃO DE ESTUDO
        log_url = reverse('studylog-list')
        log_data = {
            'course': course_id,
            'topic': topic_id,
            'date': date.today().isoformat(),
            'minutes_studied': 90,
            'notes': 'Estudei conceitos básicos de derivadas'
        }
        
        log_response = authenticated_client.post(log_url, log_data, format='json')
        assert log_response.status_code == status.HTTP_201_CREATED
        
        # 5. FAZER PERGUNTA NO CHAT
        chat_url = reverse('studychat-ask')
        chat_data = {
            'question': 'Como resolver derivadas de funções compostas?',
            'history': [],
            'topic_id': topic_id
        }
        
        chat_response = authenticated_client.post(chat_url, chat_data, format='json')
        assert chat_response.status_code == status.HTTP_200_OK
        
        # 6. GERAR E FAZER QUIZ
        quiz_url = reverse('generate-quiz')
        quiz_data = {
            'topic_id': topic_id,
            'num_easy': 1,
            'num_moderate': 1,
            'num_hard': 0
        }
        
        quiz_response = authenticated_client.post(quiz_url, quiz_data, format='json')
        assert quiz_response.status_code == status.HTTP_201_CREATED
        
        quiz_id = quiz_response.data['id']
        questions = quiz_response.data['questions']
        
        # 7. SUBMETER TENTATIVA
        attempt_url = reverse('submit-attempt')
        attempt_data = {
            'quiz_id': quiz_id,
            'answers': [
                {'question_id': questions[0]['id'], 'user_answer': 'A'},
                {'question_id': questions[1]['id'], 'user_answer': 'B'}
            ]
        }
        
        attempt_response = authenticated_client.post(attempt_url, attempt_data, format='json')
        assert attempt_response.status_code == status.HTTP_201_CREATED
        
        # 8. ANALISAR EFICÁCIA DOS ESTUDOS
        # Precisamos criar mais dados para ter uma análise significativa
        from apps.learning.models import Topic
        topic2 = Topic.objects.create(
            course_id=course_id,
            title='Integrais',
            order=2
        )
        
        # Mais logs e quizzes...
        StudyLog.objects.create(
            user=user, topic=topic2, course_id=course_id,
            date=date.today(), minutes_studied=60
        )
        
        # Criar quiz para segundo tópico
        with patch('apps.core.services.deepseek_service.gerar_quiz_completo') as quiz_mock2:
            quiz_mock2.return_value = mock_deepseek_quiz.return_value
            
            quiz2_response = authenticated_client.post(quiz_url, {
                'topic_id': topic2.id,
                'num_easy': 1,
                'num_moderate': 1,
                'num_hard': 0
            }, format='json')
            
            # Submeter tentativa para segundo quiz
            quiz2_id = quiz2_response.data['id']
            questions2 = quiz2_response.data['questions']
            
            attempt2_response = authenticated_client.post(attempt_url, {
                'quiz_id': quiz2_id,
                'answers': [
                    {'question_id': questions2[0]['id'], 'user_answer': 'A'},
                    {'question_id': questions2[1]['id'], 'user_answer': 'A'}
                ]
            }, format='json')
        
        # Agora analisar eficácia
        analytics_url = reverse('analytics-study-effectiveness')
        analytics_response = authenticated_client.get(analytics_url)
        assert analytics_response.status_code == status.HTTP_200_OK
        assert analytics_response.data['data_points'] >= 2
        
        # 9. VERIFICAR PROGRESSO GERAL
        courses_url = reverse('course-list')
        courses_response = authenticated_client.get(courses_url)
        assert courses_response.status_code == status.HTTP_200_OK
        assert len(courses_response.data) == 1
        assert len(courses_response.data[0]['topics']) >= 2
        