# apps/assessment/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.accounts.models import User
from apps.learning.models import Course, Topic
from apps.assessment.models import Quiz, Question, Attempt
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from apps.assessment.serializers import (
    QuizGenerationSerializer,
    AttemptSubmissionSerializer,
)


User = get_user_model()


class AssessmentSerializersEdgeTests(TestCase):
    def setUp(self):
        # usuário “dono”
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com", password="x"
        )
        self.course = Course.objects.create(user=self.user, title="Curso X")
        self.topic = Topic.objects.create(course=self.course, title="Tópico X")

        # outro usuário e tópico (não deveria passar na validação de ownership)
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="x"
        )
        other_course = Course.objects.create(user=self.other, title="Outro Curso")
        self.other_topic = Topic.objects.create(course=other_course, title="Outro Tópico")

        # quiz válido para os testes de AttemptSubmissionSerializer
        self.quiz = Quiz.objects.create(topic=self.topic, title="Quiz X")

        # request de DRF para injetar no context do serializer
        factory = APIRequestFactory()
        self.request = factory.post("/fake")
        self.request.user = self.user

    # --- cobre: validate_topic_id -> except Topic.DoesNotExist ---
    def test_quiz_generation_serializer_topic_not_found_or_not_owned(self):
        data = {
            "topic_id": self.other_topic.id,  # pertence a outro usuário
            # campos opcionais/valores padrão podem ser omitidos
        }
        ser = QuizGenerationSerializer(
            data=data, context={"request": self.request}
        )
        self.assertFalse(ser.is_valid())
        # mensagem exatamente como no código
        self.assertIn("Tópico não encontrado ou não pertence a você.", ser.errors["topic_id"][0])

    # --- cobre: validate_topic_id sucesso (retorna objeto Topic e não o ID) ---
    def test_quiz_generation_serializer_topic_success_returns_object(self):
        data = {"topic_id": self.topic.id}
        ser = QuizGenerationSerializer(
            data=data, context={"request": self.request}
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        # depois da validação, o campo deve ser o objeto Topic
        self.assertEqual(ser.validated_data["topic_id"].pk, self.topic.pk)

    # --- cobre: validate_quiz_id -> except Quiz.DoesNotExist ---
    def test_attempt_submission_serializer_quiz_not_found(self):
        data = {
            "quiz_id": 999999,   # inexistente
            "answers": [{"question_id": 1, "user_answer": "A"}],  # qualquer payload
        }
        ser = AttemptSubmissionSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn("Quiz não encontrado.", ser.errors["quiz_id"][0])

    # --- cobre: validate_answers lista vazia ---
    def test_attempt_submission_serializer_answers_empty(self):
        data = {
            "quiz_id": self.quiz.id,  # válido para passar do validate_quiz_id
            "answers": [],            # força o erro do validate_answers
        }
        ser = AttemptSubmissionSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn("A lista de respostas não pode estar vazia.", ser.errors["answers"][0])

class AssessmentViewEdges(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", email="u@example.com", password="p")
        self.client.force_authenticate(self.user)
        self.course = Course.objects.create(user=self.user, title="Curso X")
        self.topic = Topic.objects.create(course=self.course, title="Tópico X")

    @patch("apps.core.services.deepseek_service.gerar_quiz_completo", return_value={})
    def test_generate_quiz_ai_failure_returns_503(self, _mock_ai):
        url = reverse("generate-quiz")  # mesmo name que você já usa
        resp = self.client.post(url, {"topic_id": self.topic.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("Falha ao gerar conteúdo", str(resp.data))
        
    @patch("apps.core.services.deepseek_service.gerar_quiz_completo", side_effect=Exception("boom"))
    def test_generate_quiz_unexpected_exception_returns_500(self, _mock_ai):
        url = reverse("generate-quiz")
        resp = self.client.post(url, {"topic_id": self.topic.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", resp.data)  # Verifica se a chave 'error' existe
        self.assertIn("inesperado", resp.data["error"])  # Verifica o conteúdo da mensagem
        
    def test_quiz_viewset_filters_by_logged_user(self):
        # cria quiz do usuário logado
        q1 = Quiz.objects.create(topic=self.topic, title="Q do dono")

        # cria quiz de OUTRO usuário (não pode aparecer)
        other = User.objects.create_user(username="vizin", email="v@x.com", password="p")
        other_course = Course.objects.create(user=other, title="Outro Curso")
        other_topic = Topic.objects.create(course=other_course, title="Outro Tópico")
        q2 = Quiz.objects.create(topic=other_topic, title="Q do vizinho")

        # Chama o endpoint de listagem (use a URL concreta do seu roteador)
        resp = self.client.get("/api/assessment/quizzes/")  # pode trocar por reverse se tiver o name
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        titles = [item.get("title") or item.get("name") for item in resp.data] if isinstance(resp.data, list) \
                 else [i.get("title") for i in resp.data.get("results", [])]
        # Deve conter apenas o do usuário logado
        self.assertIn("Q do dono", titles)
        self.assertNotIn("Q do vizinho", titles)

    def test_attempt_viewset_filters_by_logged_user(self):
        # quiz do usuário logado
        quiz = Quiz.objects.create(topic=self.topic, title="Q")
        # tentativa do usuário logado
        Attempt.objects.create(user=self.user, quiz=quiz, score=100.0)

        # tentativa de outro usuário (não deve aparecer)
        other = User.objects.create_user(username="v2", email="v2@x.com", password="p")
        Attempt.objects.create(user=other, quiz=quiz, score=50.0)

        resp = self.client.get("/api/assessment/attempts/")  # idem, troque por reverse se tiver o name
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Verifica que todas as tentativas pertencem ao usuário logado
        # (lista simples ou paginada)
        items = resp.data if isinstance(resp.data, list) else resp.data.get("results", [])
        self.assertTrue(all(it.get("user") in (None, self.user.id, self.user.pk)  # caso serializer não exponha user
                            for it in items))
        # Alternativa robusta: contar por quantidade esperada
        self.assertIn(len(items), (1,))  # só 1 tentativa do user logado



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
