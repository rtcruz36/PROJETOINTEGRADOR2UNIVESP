# apps/analytics/tests.py

import datetime
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase,APIClient
import numpy as np # Usaremos numpy para o cálculo da correlação no teste
from django.test import SimpleTestCase
from django.utils import timezone

from apps.analytics.views import get_correlation_interpretation

from apps.accounts.models import User
from apps.learning.models import Course, Topic
from apps.scheduling.models import StudyLog
from apps.assessment.models import Quiz, Attempt
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model


User = get_user_model()

class StudyEffectivenessViewEdgeCases(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("apps.analytics.views.Topic.objects")
    @patch("apps.analytics.views.pearsonr")
    def test_pearsonr_exception_results_in_none(self, mock_pearsonr, mock_topic_objects):
        # Arrange: mock do queryset para produzir analysis_data com >= 2 pontos
        class MockTopic:
            def __init__(self, i, title, mins, score=None):
                self.id = i
                self.title = title
                self.total_minutes_studied = mins
                self.average_quiz_score = score

        # Criar objetos mock com dados válidos para passar pela validação
        topic1 = MockTopic(1, "A", 60)  # tem minutos estudados
        topic2 = MockTopic(2, "B", 120)  # tem minutos estudados
        quiz_topic1 = MockTopic(1, "A", 0, score=70.0)  # tem score válido
        quiz_topic2 = MockTopic(2, "B", 0, score=90.0)  # tem score válido

        # Mock do primeiro queryset (topics_with_study)
        mock_study_qs = MagicMock()
        mock_study_qs.__iter__ = lambda self: iter([topic1, topic2])
        mock_study_qs.annotate.return_value.distinct.return_value = mock_study_qs

        # Mock do segundo queryset (topics_with_quiz)
        mock_quiz_qs = MagicMock()
        
        # Mock do filter().first() para retornar os dados corretos
        def mock_filter(id):
            mock_filtered = MagicMock()
            if id == 1:
                mock_filtered.first.return_value = quiz_topic1
            elif id == 2:
                mock_filtered.first.return_value = quiz_topic2
            else:
                mock_filtered.first.return_value = None
            return mock_filtered
        
        mock_quiz_qs.filter = mock_filter
        mock_quiz_qs.annotate.return_value.distinct.return_value = mock_quiz_qs

        # Configurar o mock para retornar os querysets corretos
        def mock_filter_chain(*args, **kwargs):
            mock_qs = MagicMock()
            if 'study_logs__isnull' in str(kwargs):
                # Retorna o queryset de study
                mock_qs.annotate.return_value.distinct.return_value = mock_study_qs
                return mock_qs
            elif 'quizzes__isnull' in str(kwargs):
                # Retorna o queryset de quiz
                mock_qs.annotate.return_value.distinct.return_value = mock_quiz_qs
                return mock_qs
            return mock_qs
        
        mock_topic_objects.filter.side_effect = mock_filter_chain

        # Forçar exceção em pearsonr
        mock_pearsonr.side_effect = Exception("boom")

        # Act
        resp = self.client.get("/api/analytics/study-effectiveness/")

        # Assert
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["correlation_coefficient"])
        self.assertIn("Não há dados suficientes", resp.data["interpretation"])
        
    @patch("apps.analytics.views.Topic.objects")
    @patch("apps.analytics.views.pearsonr")
    def test_nan_returns_none(self, mock_pearsonr, mock_topic_objects):
        class MockTopic:
            def __init__(self, i, title, mins, score=None):
                self.id = i
                self.title = title
                self.total_minutes_studied = mins
                self.average_quiz_score = score

        # Criar objetos mock com dados válidos para passar pela validação
        topic1 = MockTopic(1, "A", 100)  # tem minutos estudados
        topic2 = MockTopic(2, "B", 100)  # tem minutos estudados  
        quiz_topic1 = MockTopic(1, "A", 0, score=80.0)  # tem score válido
        quiz_topic2 = MockTopic(2, "B", 0, score=80.0)  # tem score válido

        # Mock do primeiro queryset (topics_with_study)
        mock_study_qs = MagicMock()
        mock_study_qs.__iter__ = lambda self: iter([topic1, topic2])
        mock_study_qs.annotate.return_value.distinct.return_value = mock_study_qs

        # Mock do segundo queryset (topics_with_quiz)
        mock_quiz_qs = MagicMock()
        
        # Mock do filter().first() para retornar os dados corretos
        def mock_filter(id):
            mock_filtered = MagicMock()
            if id == 1:
                mock_filtered.first.return_value = quiz_topic1
            elif id == 2:
                mock_filtered.first.return_value = quiz_topic2
            else:
                mock_filtered.first.return_value = None
            return mock_filtered
        
        mock_quiz_qs.filter = mock_filter
        mock_quiz_qs.annotate.return_value.distinct.return_value = mock_quiz_qs

        # Configurar o mock para retornar os querysets corretos
        def mock_filter_chain(*args, **kwargs):
            mock_qs = MagicMock()
            if 'study_logs__isnull' in str(kwargs):
                # Retorna o queryset de study
                mock_qs.annotate.return_value.distinct.return_value = mock_study_qs
                return mock_qs
            elif 'quizzes__isnull' in str(kwargs):
                # Retorna o queryset de quiz
                mock_qs.annotate.return_value.distinct.return_value = mock_quiz_qs
                return mock_qs
            return mock_qs
        
        mock_topic_objects.filter.side_effect = mock_filter_chain

        # pearsonr devolve (nan, p)
        import math
        mock_pearsonr.return_value = (math.nan, 0.5)

        resp = self.client.get("/api/analytics/study-effectiveness/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["correlation_coefficient"])
        self.assertIn("Não há dados suficientes", resp.data["interpretation"])


class CorrelationInterpretationTests(SimpleTestCase):
    def test_none_returns_no_data_message(self):
        self.assertIn("Não há dados suficientes", get_correlation_interpretation(None))

    def test_nan_returns_no_data_message(self):
        import math
        self.assertIn("Não há dados suficientes", get_correlation_interpretation(float("nan")))

    def test_insignificant_returns_no_correlation_message(self):
        self.assertIn("Não há correlação significativa", get_correlation_interpretation(0.05))

    def test_weak_positive(self):
        msg = get_correlation_interpretation(0.2)
        self.assertIn("correlação fraca e positiva", msg)

    def test_moderate_positive(self):
        msg = get_correlation_interpretation(0.5)
        self.assertIn("correlação moderada e positiva", msg)

    def test_strong_positive(self):
        msg = get_correlation_interpretation(0.8)
        self.assertIn("correlação forte e positiva", msg)

    def test_strong_negative(self):
        msg = get_correlation_interpretation(-0.8)
        self.assertIn("correlação forte e negativa", msg)

class AnalyticsAPITests(APITestCase):

    def setUp(self):
        """
        Configuração inicial para os testes.
        """
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('analytics-study-effectiveness')

    def _create_full_topic_data(self, topic_title, minutes_studied, quiz_score):
        """
        Função auxiliar para criar um conjunto completo de dados (Tópico, Log, Quiz, Tentativa)
        para um único ponto de dados na nossa análise.
        """
        course, _ = Course.objects.get_or_create(user=self.user, title="Matemática Discreta")
        topic = Topic.objects.create(course=course, title=topic_title)
        
        # Cria o log de estudo
        StudyLog.objects.create(
            user=self.user,
            course=course,
            topic=topic,
            date=datetime.date.today(),
            minutes_studied=minutes_studied
        )
        
        # Cria o quiz e a tentativa
        quiz = Quiz.objects.create(topic=topic, title=f"Quiz de {topic_title}")
        Attempt.objects.create(
            user=self.user,
            quiz=quiz,
            score=quiz_score
        )
        return topic

    def test_study_effectiveness_strong_positive_correlation(self):
        """
        Testa o cálculo de correlação com dados que devem resultar em uma correlação positiva forte.
        """
        # Preparação: Criar dados com uma correlação clara
        # Tópico 1: Pouco estudo, nota baixa
        self._create_full_topic_data("Teoria dos Grafos", minutes_studied=30, quiz_score=55.0)
        # Tópico 2: Estudo médio, nota média
        self._create_full_topic_data("Lógica Proposicional", minutes_studied=90, quiz_score=75.0)
        # Tópico 3: Muito estudo, nota alta
        self._create_full_topic_data("Relações de Recorrência", minutes_studied=180, quiz_score=95.0)

        # Ação
        response = self.client.get(self.url)

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertEqual(data['data_points'], 3)
        self.assertIn("forte e positiva", data['interpretation'])
        
        # Verificação do cálculo
        # Usamos numpy para recalcular a correlação aqui no teste e comparar.
        tempos = [30, 90, 180]
        notas = [55.0, 75.0, 95.0]
        expected_correlation = np.corrcoef(tempos, notas)[0, 1]
        
        # Usamos assertAlmostEqual para lidar com pequenas imprecisões de ponto flutuante
        self.assertAlmostEqual(data['correlation_coefficient'], expected_correlation, places=5)
        self.assertEqual(len(data['topic_data']), 3)

    def test_study_effectiveness_no_data(self):
        """
        Testa o comportamento do endpoint quando não há dados suficientes para a análise.
        """
        # Preparação: Apenas um tópico com dados. Correlação não pode ser calculada.
        self._create_full_topic_data("Conjuntos", minutes_studied=60, quiz_score=80.0)

        # Ação
        response = self.client.get(self.url)

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertIsNone(data['correlation_coefficient'])
        self.assertEqual(data['data_points'], 1)
        self.assertIn("São necessários pelo menos dois tópicos", data['interpretation'])

    def test_study_effectiveness_ignores_incomplete_data(self):
        """
        Garante que a análise ignora tópicos que não têm tanto logs de estudo quanto notas de quiz.
        """
        # Preparação
        # Tópico 1: Dados completos (será o único incluído na análise)
        self._create_full_topic_data("Permutações", minutes_studied=45, quiz_score=88.0)
        # Tópico 2: Dados completos (será o segundo incluído na análise)
        self._create_full_topic_data("Combinações", minutes_studied=75, quiz_score=92.0)
        
        # Tópico 3: Tem estudo, mas não tem nota de quiz
        course = Course.objects.get(title="Matemática Discreta")
        topic_sem_quiz = Topic.objects.create(course=course, title="Tópico Sem Quiz")
        StudyLog.objects.create(user=self.user, course=course, topic=topic_sem_quiz, date=datetime.date.today(), minutes_studied=100)

        # Tópico 4: Tem quiz, mas não tem log de estudo
        topic_sem_estudo = Topic.objects.create(course=course, title="Tópico Sem Estudo")
        quiz = Quiz.objects.create(topic=topic_sem_estudo, title="Quiz Inútil")
        Attempt.objects.create(user=self.user, quiz=quiz, score=50.0)

        # Ação
        response = self.client.get(self.url)

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        # Apenas 2 dos 4 tópicos devem ser usados no cálculo
        self.assertEqual(data['data_points'], 2)
        self.assertIsNotNone(data['correlation_coefficient'])
        self.assertEqual(len(data['topic_data']), 2)
        
        # Verifica se os tópicos corretos foram usados
        included_topics = [d['topic_title'] for d in data['topic_data']]
        self.assertIn("Permutações", included_topics)
        self.assertIn("Combinações", included_topics)
        self.assertNotIn("Tópico Sem Quiz", included_topics)
        self.assertNotIn("Tópico Sem Estudo", included_topics)


class AdditionalAnalyticsEndpointsTests(APITestCase):
    """Testes para as novas análises disponíveis."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='dash', email='dash@example.com', password='password'
        )
        self.client.force_authenticate(self.user)
        self.course = Course.objects.create(user=self.user, title='História')
        self.topic_a = Topic.objects.create(course=self.course, title='Idade Média')
        self.topic_b = Topic.objects.create(course=self.course, title='Idade Moderna')

        today = timezone.localdate()

        # Criar logs consecutivos para formar streaks e métricas temporais
        for offset, minutes in enumerate([45, 60, 30, 90]):
            StudyLog.objects.create(
                user=self.user,
                course=self.course,
                topic=self.topic_a,
                date=today - datetime.timedelta(days=offset),
                minutes_studied=minutes,
            )

        StudyLog.objects.create(
            user=self.user,
            course=self.course,
            topic=self.topic_b,
            date=today - datetime.timedelta(days=10),
            minutes_studied=120,
        )

        quiz_a = Quiz.objects.create(topic=self.topic_a, title='Quiz A')
        quiz_b = Quiz.objects.create(topic=self.topic_b, title='Quiz B')

        attempt_dates = [
            timezone.now() - datetime.timedelta(days=5),
            timezone.now() - datetime.timedelta(days=2),
            timezone.now() - datetime.timedelta(days=1),
        ]
        scores = [55.0, 70.0, 82.0]
        for attempt_date, score in zip(attempt_dates, scores):
            attempt = Attempt.objects.create(
                user=self.user,
                quiz=quiz_a,
                score=score,
            )
            Attempt.objects.filter(id=attempt.id).update(completed_at=attempt_date)

        attempt_b = Attempt.objects.create(
            user=self.user,
            quiz=quiz_b,
            score=88.0,
        )
        Attempt.objects.filter(id=attempt_b.id).update(
            completed_at=timezone.now() - datetime.timedelta(days=3)
        )

    def test_study_progress_endpoint(self):
        response = self.client.get(reverse('analytics-study-progress'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(data['total_attempts'], 4)
        self.assertGreaterEqual(len(data['timeline']), 1)
        self.assertGreaterEqual(len(data['per_topic']), 2)
        self.assertIn('trend_summary', data)

        topic_titles = {entry['topic_title'] for entry in data['per_topic']}
        self.assertIn('Idade Média', topic_titles)
        self.assertIn('Idade Moderna', topic_titles)

    def test_topic_comparison_endpoint(self):
        response = self.client.get(reverse('analytics-topic-comparison'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(len(data['by_topic']), 2)
        self.assertEqual(len(data['by_course']), 1)
        topic_minutes = {entry['topic_title']: entry['total_minutes'] for entry in data['by_topic']}
        self.assertGreaterEqual(topic_minutes['Idade Média'], 45)
        self.assertGreaterEqual(topic_minutes['Idade Moderna'], 120)
        self.assertIn('summary', data)

    def test_engagement_metrics_endpoint(self):
        response = self.client.get(reverse('analytics-engagement-metrics'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertGreaterEqual(data['current_streak'], 1)
        self.assertGreaterEqual(data['best_streak'], data['current_streak'])
        self.assertGreater(data['total_minutes_last_7_days'], 0)
        self.assertGreaterEqual(len(data['weekly_minutes']), 1)
        self.assertIsNotNone(data['summary'])

    def test_dashboard_endpoint_combines_sections(self):
        response = self.client.get(reverse('analytics-dashboard'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertIn('study_effectiveness', data)
        self.assertIn('score_progression', data)
        self.assertIn('topic_comparison', data)
        self.assertIn('engagement_metrics', data)