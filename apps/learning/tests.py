# apps/learning/tests.py

from django.urls import reverse
from rest_framework import status
from unittest.mock import patch # Ferramenta para "mockar"
from apps.accounts.models import User
from apps.learning.models import Course, Topic, Subtopic
from django.test import TestCase
from rest_framework.test import APITestCase, APIRequestFactory
from django.contrib.auth import get_user_model
from apps.learning.views import CourseViewSet, TopicViewSet, SubtopicUpdateAPIView

User = get_user_model()


# ====== MODELS: __str__ e get_absolute_url ======

class LearningModelsExtraTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("m1", email="m1@x.com", password="p")
        self.course = Course.objects.create(user=self.user, title="Cálculo I")
        self.topic = Topic.objects.create(course=self.course, title="Derivadas", slug="derivadas")
        self.subtopic = Subtopic.objects.create(topic=self.topic, title="Regras de Derivação", order=1)

    def test_course_str(self):
        self.assertEqual(str(self.course), "Cálculo I")

    def test_topic_str(self):
        self.assertEqual(str(self.topic), "Cálculo I - Derivadas")

    def test_subtopic_str(self):
        self.assertEqual(str(self.subtopic), "Regras de Derivação")

    @patch("apps.learning.models.reverse", return_value="/topics/derivadas/")
    def test_topic_get_absolute_url(self, mock_reverse):
        url = self.topic.get_absolute_url()
        self.assertEqual(url, "/topics/derivadas/")
        mock_reverse.assert_called_once_with("topic-detail", kwargs={"slug": "derivadas"})


# ====== CREATE FLOW: normalização e nenhum subtópico ======

class LearningCreateFlowEdges(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("uL", email="u@x.com", password="p")
        self.client.force_authenticate(self.user)
        self.url = reverse("create-study-plan")

    @patch("apps.core.services.deepseek_service.sugerir_subtopicos")
    @patch("apps.core.services.deepseek_service.sugerir_plano_de_topico")
    def test_create_study_plan_normaliza_e_remove_duplicados(self, mock_plano, mock_subs):
        """
        Cobre o laço de normalização:
        - remove vazios/whitespace
        - remove duplicados (case-insensitive)
        - mantém ordem e começa em 1 ao criar
        """
        mock_plano.return_value = "Plano gerado"
        mock_subs.return_value = ["  Sub 1 ", "sub 1", "", "Sub 2", "  "]

        data = {
            "course_title": "Física Quântica",
            "topic_title": "Princípio da Incerteza",
            "course_description": "Intro",
        }
        resp = self.client.post(self.url, data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        topic = Topic.objects.get(title="Princípio da Incerteza")
        created = list(Subtopic.objects.filter(topic=topic).order_by("order").values_list("title", "order"))
        self.assertEqual(created, [("Sub 1", 1), ("Sub 2", 2)])  # sem duplicados/vazios, ordem iniciando em 1

    @patch("apps.learning.views.logger")  # para executar e cobrir o logger.warning do else
    @patch("apps.core.services.deepseek_service.sugerir_subtopicos")
    @patch("apps.core.services.deepseek_service.sugerir_plano_de_topico")
    def test_create_study_plan_sem_subtopicos_dispara_warning(self, mock_plano, mock_subs, mock_logger):
        mock_plano.return_value = "Plano gerado"
        mock_subs.return_value = []  # força o caminho do 'else: logger.warning(...)'

        data = {
            "course_title": "Álgebra Linear",
            "topic_title": "Vetores",
            "course_description": "",
        }
        resp = self.client.post(self.url, data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        topic = Topic.objects.get(title="Vetores")
        self.assertFalse(Subtopic.objects.filter(topic=topic).exists())
        mock_logger.warning.assert_called()  # linha do warning coberta


# ====== VIEWSETS/VIEW: get_queryset filtrando por usuário ======

class LearningViewsetsQuerysetEdges(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user("q1", email="q1@x.com", password="p")
        self.other = User.objects.create_user("q2", email="q2@x.com", password="p")

        # cursos e tópicos do usuário
        self.course_u = Course.objects.create(user=self.user, title="Curso do U")
        self.topic_u = Topic.objects.create(course=self.course_u, title="Tópico do U", slug="t-u")
        Subtopic.objects.create(topic=self.topic_u, title="S1", order=1)

        # cursos e tópicos de outro usuário
        self.course_o = Course.objects.create(user=self.other, title="Curso do O")
        self.topic_o = Topic.objects.create(course=self.course_o, title="Tópico do O", slug="t-o")
        Subtopic.objects.create(topic=self.topic_o, title="S2", order=1)

    def test_course_viewset_get_queryset_filtra_por_user(self):
        request = self.factory.get("/fake")
        request.user = self.user
        view = CourseViewSet()
        view.request = request
        qs = view.get_queryset()
        self.assertTrue(all(c.user_id == self.user.id for c in qs))
        self.assertIn(self.course_u, qs)
        self.assertNotIn(self.course_o, qs)

    def test_topic_viewset_get_queryset_filtra_por_user(self):
        request = self.factory.get("/fake")
        request.user = self.user
        view = TopicViewSet()
        view.request = request
        qs = view.get_queryset()
        self.assertTrue(all(t.course.user_id == self.user.id for t in qs))
        self.assertIn(self.topic_u, qs)
        self.assertNotIn(self.topic_o, qs)

    def test_subtopic_update_apiview_get_queryset_filtra_por_user(self):
        """
        Tenta acessar um Subtopic de outro usuário via queryset filtrado → não encontra (404 no fluxo real).
        Aqui cobrimos a linha do retorno filtrado.
        """
        request = self.factory.get("/fake")
        request.user = self.user
        view = SubtopicUpdateAPIView()
        view.request = request
        qs = view.get_queryset()
        # Apenas subtopics do usuário self.user
        self.assertTrue(all(s.topic.course.user_id == self.user.id for s in qs))
        # o subtopic do outro usuário não está no queryset
        self.assertFalse(qs.filter(pk__in=Subtopic.objects.filter(topic=self.topic_o).values_list("pk", flat=True)).exists())


class LearningAPITests(APITestCase):

    def setUp(self):
        """Configuração inicial para todos os testes nesta classe."""
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user) # Força a autenticação para não precisar fazer login sempre
        self.url = reverse('create-study-plan')

    # O decorador @patch substitui a função do deepseek_service durante o teste
    @patch('apps.core.services.deepseek_service.sugerir_subtopicos')
    @patch('apps.core.services.deepseek_service.sugerir_plano_de_topico')
    def test_create_study_plan_flow(self, mock_sugerir_plano, mock_sugerir_subtopicos):
        """
        Testa o endpoint principal de criação, garantindo que a IA é chamada
        e os objetos são criados corretamente.
        """
        # Preparação: Definimos o que as funções "mockadas" devem retornar
        mock_sugerir_plano.return_value = "Este é um plano de estudos detalhado."
        mock_sugerir_subtopicos.return_value = ["Subtópico 1", "Subtópico 2", "Subtópico 3"]

        data = {
            "course_title": "Física Quântica",
            "topic_title": "O Princípio da Incerteza",
            "course_description": "Uma introdução."
        }

        # Ação
        response = self.client.post(self.url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verifica se os objetos foram criados no banco
        self.assertTrue(Course.objects.filter(title="Física Quântica").exists())
        self.assertTrue(Topic.objects.filter(title="O Princípio da Incerteza").exists())
        self.assertEqual(Subtopic.objects.count(), 3)
        
        # Verifica se as funções da IA foram chamadas
        mock_sugerir_plano.assert_called_once()
        mock_sugerir_subtopicos.assert_called_once()

        # Verifica o conteúdo da resposta
        self.assertEqual(response.data['title'], "O Princípio da Incerteza")
        self.assertEqual(len(response.data['subtopics']), 3)
