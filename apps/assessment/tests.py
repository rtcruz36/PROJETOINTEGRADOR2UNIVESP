# apps/assessment/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.accounts.models import User
from apps.learning.models import Course, Topic
from apps.assessment.models import Quiz, Question, Attempt

class AssessmentAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        # Dados de base para os testes
        self.course = Course.objects.create(user=self.user, title="História Antiga")
        self.topic = Topic.objects.create(course=self.course, title="Roma Antiga")

    @patch('apps.core.services.deepseek_service.gerar_quiz_completo')
    def test_generate_quiz(self, mock_gerar_quiz):
        """Testa a geração de um quiz, mockando a chamada à IA."""
        # Preparação: Mock da resposta da IA
        mock_gerar_quiz.return_value = {
            "quiz_title": "Quiz sobre a República Romana",
            "quiz_description": "Teste seus conhecimentos.",
            "questions": [
                {
                    "question_text": "Quem foi o primeiro imperador de Roma?",
                    "choices": {"A": "Júlio César", "B": "Augusto", "C": "Nero", "D": "Marco Aurélio"},
                    "correct_answer": "B",
                    "difficulty": "EASY",
                    "explanation": "Augusto foi o primeiro imperador."
                }
            ]
        }
        
        url = reverse('generate-quiz')
        data = {"topic_id": self.topic.id}

        # Ação
        response = self.client.post(url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Quiz.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 1)
        
        quiz = Quiz.objects.first()
        self.assertEqual(quiz.title, "Quiz sobre a República Romana")
        self.assertEqual(quiz.topic, self.topic)
        mock_gerar_quiz.assert_called_once_with(topico=self.topic, num_faceis=7, num_moderadas=7, num_dificeis=6)

    def test_submit_attempt(self):
        """Testa a submissão de uma tentativa de quiz e o cálculo da nota."""
        # Preparação: Cria um quiz e perguntas manualmente para o teste
        quiz = Quiz.objects.create(topic=self.topic, title="Teste Manual")
        q1 = Question.objects.create(quiz=quiz, question_text="2+2?", choices={"A": "4", "B": "5"}, correct_answer="A")
        q2 = Question.objects.create(quiz=quiz, question_text="Capital da França?", choices={"A": "Berlim", "B": "Paris"}, correct_answer="B")

        url = reverse('submit-attempt')
        data = {
            "quiz_id": quiz.id,
            "answers": [
                {"question_id": q1.id, "user_answer": "A"}, # Resposta correta
                {"question_id": q2.id, "user_answer": "Berlim"} # Resposta incorreta
            ]
        }

        # Ação
        response = self.client.post(url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Attempt.objects.count(), 1)
        
        attempt = Attempt.objects.first()
        self.assertEqual(attempt.user, self.user)
        self.assertEqual(attempt.quiz, quiz)
        self.assertEqual(attempt.correct_answers_count, 1)
        self.assertEqual(attempt.incorrect_answers_count, 1)
        self.assertEqual(attempt.score, 50.0)
