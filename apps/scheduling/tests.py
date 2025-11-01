# apps/scheduling/tests.py

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.accounts.models import User
from apps.learning.models import Course, Topic, Subtopic
from apps.scheduling.models import StudyPlan, StudyLog

User = get_user_model()


class SchedulingViewsetsQuerysetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", email="u@x.com", password="p")
        self.client.force_authenticate(self.user)

        # dois cursos (um do usuário, outro de outrem)
        self.course_own = Course.objects.create(user=self.user, title="Meu Curso")
        other = User.objects.create_user("v", email="v@x.com", password="p")
        self.course_other = Course.objects.create(user=other, title="Outro Curso")

        # planos do usuário
        self.plan1 = StudyPlan.objects.create(user=self.user, course=self.course_own, day_of_week=0, minutes_planned=30)
        self.plan2 = StudyPlan.objects.create(user=self.user, course=self.course_own, day_of_week=1, minutes_planned=45)
        # plano de outro usuário (não deve aparecer)
        StudyPlan.objects.create(user=other, course=self.course_other, day_of_week=2, minutes_planned=60)

    def test_studyplan_viewset_get_queryset_filtra_por_user_e_course_id(self):
        # 1) lista geral: só do usuário
        resp_all = self.client.get(reverse("studyplan-list"))
        self.assertEqual(resp_all.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in resp_all.data}
        self.assertSetEqual(ids, {self.plan1.id, self.plan2.id})

        # 2) com ?course_id= filtra ainda mais (cobre linha vermelha do filter(course_id=...))
        resp_filtered = self.client.get(reverse("studyplan-list"), {"course_id": self.course_own.id})
        self.assertEqual(resp_filtered.status_code, status.HTTP_200_OK)
        self.assertTrue(all(i["course"] == self.course_own.id for i in resp_filtered.data))

    def test_studylog_viewset_get_queryset_filtra_por_user_e_perform_create_define_user(self):
        # cria um curso/tópico próprios
        topic = Topic.objects.create(course=self.course_own, title="Tópico")
        # cria StudyLog de outro usuário (não deve aparecer)
        other = User.objects.create_user("z", email="z@x.com", password="p")
        StudyLog.objects.create(user=other, course=self.course_other, topic=topic,
                                date=timezone.now().date(), minutes_studied=5)

        # POST sem campo user: perform_create deve setar user=request.user
        payload = {
            "course": self.course_own.id,
            "topic": topic.id,
            "date": timezone.now().date().isoformat(),
            "minutes_studied": 25,
            "notes": "estudo"
        }
        create = self.client.post(reverse("studylog-list"), payload, format="json")
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        created = StudyLog.objects.get(id=create.data["id"])
        self.assertEqual(created.user, self.user)

        # GET: queryset deve trazer apenas logs do usuário
        resp = self.client.get(reverse("studylog-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(item["course"] == self.course_own.id for item in resp.data))


class SchedulingGenerateScheduleEdges(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u2", email="u2@x.com", password="p")
        self.client.force_authenticate(self.user)

        self.course = Course.objects.create(user=self.user, title="Curso X")
        self.topic = Topic.objects.create(course=self.course, title="Tópico X")
        # subtopics serão criados/delidos por teste

    def test_generate_schedule_missing_topic_id_returns_400(self):
    # Simula uma requisição sem o campo 'topic_id'
        resp = self.client.post('/api/scheduling/generate-schedule/', {}, format='json')

    # Verifica se o status code é 400 (Bad Request)
        self.assertEqual(resp.status_code, 400)

    # Verifica se a mensagem de erro correta está presente na resposta
        self.assertIn("O campo 'topic_id' é obrigatório.", str(resp.data))
    
    def test_generate_schedule_no_subtopics_returns_404(self):
        # nenhum Subtopic criado
        url = reverse("generate-schedule")
        resp = self.client.post(url, {"topic_id": self.topic.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("não possui subtópicos", str(resp.data))

    def test_generate_schedule_without_studyplan_returns_400(self):
        # cobre a mensagem “Você precisa definir um plano de estudo...”
        # (já tem teste similar, manteremos um garantidor aqui também)
        url = reverse("generate-schedule")
        Subtopic.objects.create(topic=self.topic, title="S1", order=1)
        resp = self.client.post(url, {"topic_id": self.topic.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("precisa definir um plano de estudo", str(resp.data))

    @patch("apps.scheduling.views.deepseek_service.distribuir_subtopicos_no_cronograma", return_value={})
    def test_generate_schedule_ai_retorna_vazio_503(self, _mock_service):
        # prepara dados mínimos
        Subtopic.objects.create(topic=self.topic, title="S1", order=1)
        StudyPlan.objects.create(user=self.user, course=self.course, day_of_week=0, minutes_planned=60)
        url = reverse("generate-schedule")
        resp = self.client.post(url, {"topic_id": self.topic.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch("apps.scheduling.views.deepseek_service.distribuir_subtopicos_no_cronograma", side_effect=Exception("boom"))
    def test_generate_schedule_ai_explodiu_500(self, _mock_service):
        Subtopic.objects.create(topic=self.topic, title="S1", order=1)
        StudyPlan.objects.create(user=self.user, course=self.course, day_of_week=0, minutes_planned=60)
        url = reverse("generate-schedule")
        resp = self.client.post(url, {"topic_id": self.topic.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("inesperado", str(resp.data).lower())


class SchedulingSerializersValidationEdges(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("s1", email="s1@x.com", password="p")
        self.client.force_authenticate(self.user)
        self.course_own = Course.objects.create(user=self.user, title="Meu")
        self.topic = Topic.objects.create(course=self.course_own, title="Top")
        self.other = User.objects.create_user("s2", email="s2@x.com", password="p")
        self.course_other = Course.objects.create(user=self.other, title="Alheio")

    def test_studyplan_serializer_bloqueia_curso_de_outro_usuario(self):
        url = reverse("studyplan-list")
        payload = {"course": self.course_other.id, "day_of_week": 3, "minutes_planned": 40}
        resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # cobre a mensagem do ValidationError no serializer
        self.assertIn("Você só pode criar planos de estudo", str(resp.data))

    def test_studylog_serializer_bloqueia_curso_de_outro_usuario(self):
        url = reverse("studylog-list")
        payload = {
            "course": self.course_other.id,          # curso de outro usuário (deve falhar)
            "topic": self.topic.id,                   # topic não condizente com o curso → ainda falha no curso
            "date": timezone.now().date().isoformat(),
            "minutes_studied": 10,
            "notes": "",
        }
        resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("só pode registrar estudos", str(resp.data))  # mensagem do ValidationError


class SchedulingAPITests(APITestCase):

    def setUp(self):
        """
        Configuração inicial para os testes, criando usuário, curso, tópico e subtópicos.
        """
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        
        self.course = Course.objects.create(user=self.user, title="Engenharia de Software")
        self.topic = Topic.objects.create(course=self.course, title="Metodologias Ágeis")
        
        # Criamos subtópicos manualmente para usar no teste de geração de cronograma
        self.subtopic1 = Subtopic.objects.create(topic=self.topic, title="Scrum", order=0)
        self.subtopic2 = Subtopic.objects.create(topic=self.topic, title="Kanban", order=1)

    def test_create_and_list_study_plan(self):
        """
        Garante que um usuário pode criar uma meta de estudo e depois listá-la.
        """
        # --- Teste de Criação ---
        create_url = reverse('studyplan-list') # A URL do ViewSet para POST e GET (lista)
        data = {
            "course": self.course.id,
            "day_of_week": 0,  # Segunda-feira
            "minutes_planned": 90
        }

        # Ação de Criação
        response_create = self.client.post(create_url, data, format='json')

        # Verificação da Criação
        self.assertEqual(response_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StudyPlan.objects.count(), 1)
        
        plan = StudyPlan.objects.first()
        self.assertEqual(plan.user, self.user)
        self.assertEqual(plan.course, self.course)
        self.assertEqual(plan.minutes_planned, 90)

        # --- Teste de Listagem ---
        # Ação de Listagem
        response_list = self.client.get(create_url)

        # Verificação da Listagem
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list.data), 1)
        self.assertEqual(response_list.data[0]['minutes_planned'], 90)
        self.assertEqual(response_list.data[0]['day_of_week_display'], 'Segunda-feira')

    @patch('apps.core.services.deepseek_service.distribuir_subtopicos_no_cronograma')
    def test_generate_schedule_flow(self, mock_distribuir_subtopicos):
        """
        Testa o endpoint de geração de cronograma, mockando a chamada à IA.
        """
        # Preparação 1: Criar as metas de estudo (StudyPlan) que a IA vai usar
        StudyPlan.objects.create(user=self.user, course=self.course, day_of_week=0, minutes_planned=60) # Seg
        StudyPlan.objects.create(user=self.user, course=self.course, day_of_week=2, minutes_planned=60) # Qua

        # Preparação 2: Definir o que a função mockada da IA deve retornar
        mock_distribuir_subtopicos.return_value = {
            "Segunda-feira": [
                {"subtopic": "Scrum", "estimated_time": 45, "difficulty": "Médio"}
            ],
            "Terça-feira": [],
            "Quarta-feira": [
                {"subtopic": "Kanban", "estimated_time": 30, "difficulty": "Fácil"}
            ],
            "Quinta-feira": [],
            "Sexta-feira": [],
            "Sábado": [],
            "Domingo": []
        }

        url = reverse('generate-schedule')
        data = {"topic_id": self.topic.id}

        # Ação
        response = self.client.post(url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verifica se a função da IA foi chamada com os argumentos corretos
        # Pegamos os planos de estudo e subtópicos para garantir que a view os passou corretamente
        planos_de_estudo = list(StudyPlan.objects.filter(user=self.user, course=self.course))
        subtopicos_titulos = list(self.topic.subtopics.values_list('title', flat=True).order_by('order'))
        
        mock_distribuir_subtopicos.assert_called_once()
        # Verificamos a chamada da função mockada. É um pouco complexo, mas garante que a view está funcionando.
        # O primeiro argumento da chamada é 'args', o segundo é 'kwargs'.
        call_args, call_kwargs = mock_distribuir_subtopicos.call_args
        self.assertEqual(call_kwargs['topico'], self.topic)
        self.assertListEqual(call_kwargs['subtopicos'], subtopicos_titulos)
        self.assertListEqual(call_kwargs['planos_de_estudo'], planos_de_estudo)

        # Verifica se a resposta da API foi estruturada corretamente
        self.assertIn('weekly_plan', response.data)
        self.assertIn('summary', response.data)

        weekly_plan = {dia['day_name']: dia for dia in response.data['weekly_plan']}
        self.assertIn('Segunda-feira', weekly_plan)
        self.assertEqual(weekly_plan['Segunda-feira']['sessions'][0]['subtopic'], "Scrum")
        self.assertIn('Terça-feira', weekly_plan)
        self.assertEqual(len(weekly_plan['Terça-feira']['sessions']), 0)
        self.assertEqual(response.data['summary']['total_estimated_minutes'], 75)

    def test_generate_schedule_without_study_plan(self):
        """
        Garante que o endpoint retorna um erro se o usuário não tiver metas de estudo definidas.
        """
        # Preparação: NENHUM StudyPlan é criado.
        
        url = reverse('generate-schedule')
        data = {"topic_id": self.topic.id}

        # Ação
        response = self.client.post(url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Você precisa definir um plano de estudo", response.data['error'])


class SchedulingInsightsEndpointsTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='insights', email='insights@example.com', password='password'
        )
        self.client.force_authenticate(self.user)

        self.course = Course.objects.create(user=self.user, title="Algoritmos")
        self.topic = Topic.objects.create(course=self.course, title="Estruturas de Dados")

        today = timezone.localdate()
        self.monday = today - timedelta(days=today.weekday())
        self.tuesday = self.monday + timedelta(days=1)

        self.plan_monday = StudyPlan.objects.create(
            user=self.user,
            course=self.course,
            day_of_week=0,
            minutes_planned=60,
        )
        self.plan_wednesday = StudyPlan.objects.create(
            user=self.user,
            course=self.course,
            day_of_week=2,
            minutes_planned=90,
        )

        StudyLog.objects.create(
            user=self.user,
            course=self.course,
            topic=self.topic,
            date=self.monday,
            minutes_studied=45,
        )
        StudyLog.objects.create(
            user=self.user,
            course=self.course,
            topic=self.topic,
            date=self.tuesday,
            minutes_studied=30,
        )

    def test_current_week_schedule_endpoint(self):
        url = reverse('current-week-schedule')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('days', response.data)

        monday_data = next(day for day in response.data['days'] if day['day_of_week'] == 0)
        self.assertEqual(monday_data['planned_minutes'], 60)
        self.assertEqual(monday_data['completed_minutes'], 45)

    def test_weekly_progress_endpoint(self):
        url = reverse('weekly-progress')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall']['planned_minutes'], 150)
        self.assertEqual(response.data['overall']['completed_minutes'], 75)

        course_entry = response.data['courses'][0]
        self.assertAlmostEqual(course_entry['completion_percentage'], 50.0)

    def test_study_reminders_endpoint(self):
        url = reverse('study-reminders')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['reminders']), 2)
        self.assertTrue(all('message' in item for item in response.data['reminders']))

    def test_study_statistics_endpoint(self):
        url = reverse('study-statistics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['totals']['minutes_studied'], 75)
        self.assertGreaterEqual(response.data['streaks']['longest_streak'], 1)
        self.assertIsNotNone(response.data['top_course'])