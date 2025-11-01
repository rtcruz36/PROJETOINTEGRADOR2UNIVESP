# tests/conftest.py
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch, MagicMock

from apps.learning.models import Course, Topic, Subtopic
from apps.scheduling.models import StudyPlan, StudyLog
from apps.assessment.models import Quiz, Question, Attempt, Answer

User = get_user_model()

@pytest.fixture
def api_client():
    """Cliente da API REST."""
    return APIClient()


@pytest.fixture
def media_storage(tmp_path, settings):
    """Configura um diretório temporário para arquivos de mídia."""
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = media_root
    settings.MEDIA_URL = '/media/'

    profile_pics_dir = media_root / 'profile_pics'
    profile_pics_dir.mkdir(parents=True, exist_ok=True)

    return media_root

@pytest.fixture
def user():
    """Usuário de teste."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123',
        first_name='Test',
        last_name='User'
    )

@pytest.fixture
def other_user():
    """Outro usuário para testar isolamento de dados."""
    return User.objects.create_user(
        username='otheruser',
        email='other@example.com',
        password='testpass123'
    )

@pytest.fixture
def authenticated_client(api_client, user):
    """Cliente autenticado com JWT."""
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client

@pytest.fixture
def course(user):
    """Curso de teste."""
    return Course.objects.create(
        user=user,
        title='Cálculo I',
        description='Disciplina de Cálculo Diferencial e Integral'
    )

@pytest.fixture
def topic(course):
    """Tópico de teste."""
    return Topic.objects.create(
        course=course,
        title='Derivadas',
        suggested_study_plan='Plano de estudo para derivadas...',
        order=1
    )

@pytest.fixture
def subtopics(topic):
    """Lista de subtópicos de teste."""
    subtopics = []
    for i, title in enumerate(['Conceito de Derivada', 'Regras de Derivação', 'Derivadas de Funções Compostas'], 1):
        subtopic = Subtopic.objects.create(
            topic=topic,
            title=title,
            order=i,
            details=f'Detalhes do subtópico {title}'
        )
        subtopics.append(subtopic)
    return subtopics

@pytest.fixture
def study_plan(user, course):
    """Plano de estudo de teste."""
    return StudyPlan.objects.create(
        user=user,
        course=course,
        day_of_week=0,  # Segunda-feira
        minutes_planned=60
    )

@pytest.fixture
def study_log(user, course, topic):
    """Log de estudo de teste."""
    from datetime import date
    return StudyLog.objects.create(
        user=user,
        topic=topic,
        course=course,
        date=date.today(),
        minutes_studied=45,
        notes='Estudei derivadas hoje'
    )

@pytest.fixture
def quiz(topic):
    """Quiz de teste."""
    return Quiz.objects.create(
        topic=topic,
        title='Quiz sobre Derivadas',
        description='Teste seus conhecimentos sobre derivadas',
        total_questions=2
    )

@pytest.fixture
def questions(quiz, subtopics):
    """Perguntas de teste para o quiz."""
    questions = []
    
    question1 = Question.objects.create(
        quiz=quiz,
        subtopic=subtopics[0],
        question_text='Qual é a derivada de x²?',
        choices={'A': '2x', 'B': 'x', 'C': '2', 'D': 'x²'},
        correct_answer='A',
        difficulty='EASY',
        explanation='A derivada de x² é 2x pela regra da potência.'
    )
    
    question2 = Question.objects.create(
        quiz=quiz,
        subtopic=subtopics[1],
        question_text='Qual é a derivada de sen(x)?',
        choices={'A': 'sen(x)', 'B': 'cos(x)', 'C': '-cos(x)', 'D': '-sen(x)'},
        correct_answer='B',
        difficulty='MODERATE',
        explanation='A derivada de sen(x) é cos(x).'
    )
    
    questions.extend([question1, question2])
    return questions

@pytest.fixture
def mock_deepseek_success():
    """Mock para respostas de sucesso da API DeepSeek."""
    with patch('apps.core.services.deepseek_service._call_deepseek_api') as mock:
        mock.return_value = {
            'choices': [{
                'message': {
                    'content': 'Resposta mocada da IA'
                }
            }]
        }
        yield mock

@pytest.fixture
def mock_deepseek_quiz():
    """Mock específico para geração de quiz."""
    quiz_data = {
        'quiz_title': 'Quiz sobre Derivadas - Gerado por IA',
        'quiz_description': 'Teste seus conhecimentos sobre derivadas',
        'questions': [
            {
                'question_text': 'Qual é a derivada de x³?',
                'choices': {'A': '3x²', 'B': '3x', 'C': 'x²', 'D': '3'},
                'correct_answer': 'A',
                'difficulty': 'EASY',
                'explanation': 'Pela regra da potência: d/dx(xⁿ) = n·xⁿ⁻¹'
            },
            {
                'question_text': 'Qual é a derivada de ln(x)?',
                'choices': {'A': 'x', 'B': '1/x', 'C': 'ln(x)', 'D': 'e^x'},
                'correct_answer': 'B',
                'difficulty': 'MODERATE',
                'explanation': 'A derivada de ln(x) é 1/x'
            }
        ]
    }
    
    with patch('apps.core.services.deepseek_service.gerar_quiz_completo') as mock:
        mock.return_value = quiz_data
        yield mock

@pytest.fixture
def mock_deepseek_subtopicos():
    """Mock para sugestão de subtópicos."""
    with patch('apps.core.services.deepseek_service.sugerir_subtopicos') as mock:
        mock.return_value = [
            'Conceito de Limite',
            'Propriedades dos Limites',
            'Limites Infinitos',
            'Continuidade de Funções'
        ]
        yield mock

@pytest.fixture
def mock_deepseek_plano():
    """Mock para sugestão de plano de estudo."""
    with patch('apps.core.services.deepseek_service.sugerir_plano_de_topico') as mock:
        mock.return_value = """
# Plano de Estudo: Limites

## Objetivos
- Compreender o conceito intuitivo de limite
- Aplicar propriedades dos limites

## Cronograma
1. **Semana 1**: Conceito intuitivo
2. **Semana 2**: Definição formal
3. **Semana 3**: Propriedades e aplicações
        """
        yield mock