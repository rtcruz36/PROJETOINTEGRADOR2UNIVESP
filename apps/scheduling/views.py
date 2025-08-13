# apps/scheduling/views.py

from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import StudyPlan, StudyLog
from .serializers import StudyPlanSerializer, StudyLogSerializer
from apps.learning.models import Topic, Subtopic
from apps.core.services import deepseek_service

class StudyPlanViewSet(viewsets.ModelViewSet):
    """
    API para gerenciar as Metas de Estudo Semanais (StudyPlan).
    - GET: /api/scheduling/plans/ (lista todas as metas)
    - POST: /api/scheduling/plans/ (cria uma nova meta)
    - PUT/PATCH: /api/scheduling/plans/{id}/ (atualiza uma meta)
    - DELETE: /api/scheduling/plans/{id}/ (deleta uma meta)
    """
    queryset = StudyPlan.objects.all()
    serializer_class = StudyPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra os planos para retornar apenas os do usuário logado."""
        user = self.request.user
        # Permite filtrar por disciplina, ex: /api/scheduling/plans/?course_id=1
        course_id = self.request.query_params.get('course_id')
        queryset = self.queryset.filter(user=user)
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        return queryset.select_related('course')

    def perform_create(self, serializer):
        """Associa o plano de estudo ao usuário logado ao salvar."""
        serializer.save(user=self.request.user)

class GenerateScheduleAPIView(APIView):
    """
    Endpoint para gerar um cronograma de estudo detalhado para um tópico.
    Esta é a view que chama o serviço da IA para distribuir os subtópicos.
    URL: POST /api/scheduling/generate-schedule/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Espera um 'topic_id' no corpo da requisição.
        """
        topic_id = request.data.get('topic_id')
        if not topic_id:
            return Response(
                {"error": "O campo 'topic_id' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Validar e buscar os objetos necessários
        user = request.user
        topic = get_object_or_404(Topic, id=topic_id, course__user=user)
        subtopics = list(topic.subtopics.values_list('title', flat=True).order_by('order'))
        
        if not subtopics:
            return Response(
                {"error": "Este tópico não possui subtópicos para distribuir."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Busca os planos de estudo (metas) do usuário para a disciplina deste tópico
        study_plans = StudyPlan.objects.filter(user=user, course=topic.course)
        if not study_plans.exists():
            return Response(
                {"error": "Você precisa definir um plano de estudo (metas) para esta disciplina antes de gerar um cronograma."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Chamar o serviço do Core para fazer a distribuição
        try:
            # A função da IA faz todo o trabalho pesado de estimar, ordenar e distribuir
            distributed_schedule = deepseek_service.distribuir_subtopicos_no_cronograma(
                topico=topic,
                subtopicos=subtopics,
                planos_de_estudo=list(study_plans)
            )

            if not distributed_schedule:
                 return Response(
                    {"error": "Não foi possível gerar o cronograma. A IA pode não ter retornado dados válidos."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # 3. Retornar o cronograma gerado como resposta
            return Response(distributed_schedule, status=status.HTTP_200_OK)

        except Exception as e:
            # Logar o erro `e` em um sistema de monitoramento seria ideal
            return Response(
                {"error": f"Ocorreu um erro inesperado ao gerar o cronograma: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class StudyLogViewSet(viewsets.ModelViewSet):
    """
    API para gerenciar os Registros de Estudo (StudyLog).
    Permite que o usuário registre as sessões de estudo que completou.
    """
    queryset = StudyLog.objects.all()
    serializer_class = StudyLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra os registros para retornar apenas os do usuário logado."""
        return self.queryset.filter(user=self.request.user).select_related('course', 'topic')

    def perform_create(self, serializer):
        """Associa o registro de estudo ao usuário logado."""
        serializer.save(user=self.request.user)

