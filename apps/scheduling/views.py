# apps/scheduling/views.py

from collections import defaultdict
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.services import deepseek_service
from apps.learning.models import Topic

from .models import StudyLog, StudyPlan
from .serializers import (
    StudyLogSerializer,
    StudyPlanFilterSerializer,
    StudyPlanSerializer,
)

class StudyPlanViewSet(viewsets.ModelViewSet):
    queryset = StudyPlan.objects.all()
    serializer_class = StudyPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Primeiro filtra por usuário
        queryset = self.queryset.filter(user=self.request.user)
        
        # Depois aplica filtros adicionais se fornecidos
        filter_serializer = StudyPlanFilterSerializer(data=self.request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        
        course_id = filter_serializer.validated_data.get('course_id')
        if course_id is not None:
            queryset = queryset.filter(course_id=course_id)
        
        return queryset
        
    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError({
                "detail": "Já existe um plano de estudo para este curso neste dia."
            })
            
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

            # 3. Estruturar o cronograma para facilitar o consumo pelo frontend
            dias_semana_map = {dia_nome: dia_num for dia_num, dia_nome in StudyPlan.DayOfWeek.choices}
            weekly_plan = []
            total_minutes = 0

            for dia_nome, atividades in distributed_schedule.items():
                day_number = dias_semana_map.get(dia_nome)
                allocated_minutes = sum(item.get("estimated_time", 0) for item in atividades)
                total_minutes += allocated_minutes
                weekly_plan.append(
                    {
                        "day_name": dia_nome,
                        "day_of_week": day_number,
                        "allocated_minutes": allocated_minutes,
                        "sessions": atividades,
                    }
                )

            response_payload = {
                "topic": {
                    "id": topic.id,
                    "title": topic.title,
                    "course_id": topic.course_id,
                    "course_title": topic.course.title,
                },
                "weekly_plan": weekly_plan,
                "summary": {
                    "total_estimated_minutes": total_minutes,
                    "days_with_study": sum(1 for dia in weekly_plan if dia["allocated_minutes"] > 0),
                },
            }

            return Response(response_payload, status=status.HTTP_200_OK)

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


class CurrentWeekScheduleAPIView(APIView):
    """Retorna o cronograma planejado e concluído para a semana atual."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        today = timezone.localdate()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        study_plans = (
            StudyPlan.objects.filter(user=user)
            .select_related("course")
            .order_by("day_of_week", "course__title")
        )
        study_logs = (
            StudyLog.objects.filter(user=user, date__range=(start_of_week, end_of_week))
            .select_related("course", "topic")
            .order_by("date", "created_at")
        )

        plans_by_day = defaultdict(list)
        for plan in study_plans:
            plans_by_day[plan.day_of_week].append(plan)

        logs_by_day = defaultdict(list)
        for log in study_logs:
            logs_by_day[log.date.weekday()].append(log)

        dias_semana = dict(StudyPlan.DayOfWeek.choices)
        days_payload = []
        total_planned = 0
        total_completed = 0

        for offset in range(7):
            dia_data = start_of_week + timedelta(days=offset)
            planned_sessions = [
                {
                    "plan_id": plan.id,
                    "course_id": plan.course_id,
                    "course_title": plan.course.title,
                    "minutes_planned": plan.minutes_planned,
                }
                for plan in plans_by_day.get(offset, [])
            ]
            completed_sessions = [
                {
                    "log_id": log.id,
                    "course_id": log.course_id,
                    "course_title": log.course.title,
                    "topic_id": log.topic_id,
                    "topic_title": log.topic.title if log.topic else None,
                    "minutes_studied": log.minutes_studied,
                    "notes": log.notes,
                }
                for log in logs_by_day.get(offset, [])
            ]

            planned_minutes = sum(item["minutes_planned"] for item in planned_sessions)
            completed_minutes = sum(item["minutes_studied"] for item in completed_sessions)

            total_planned += planned_minutes
            total_completed += completed_minutes

            days_payload.append(
                {
                    "day_of_week": offset,
                    "day_name": dias_semana[offset],
                    "date": dia_data,
                    "planned_minutes": planned_minutes,
                    "planned_sessions": planned_sessions,
                    "completed_minutes": completed_minutes,
                    "completed_sessions": completed_sessions,
                }
            )

        response_data = {
            "week_start": start_of_week,
            "week_end": end_of_week,
            "total_planned_minutes": total_planned,
            "total_completed_minutes": total_completed,
            "days": days_payload,
        }

        return Response(response_data)


class WeeklyProgressAPIView(APIView):
    """Apresenta o progresso semanal planejado versus executado por disciplina."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        today = timezone.localdate()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        study_plans = StudyPlan.objects.filter(user=user).select_related("course")
        study_logs = (
            StudyLog.objects.filter(user=user, date__range=(start_of_week, end_of_week))
            .select_related("course")
        )

        planned_by_course = defaultdict(int)
        course_titles = {}
        for plan in study_plans:
            planned_by_course[plan.course_id] += plan.minutes_planned
            course_titles[plan.course_id] = plan.course.title

        studied_by_course = defaultdict(int)
        for log in study_logs:
            studied_by_course[log.course_id] += log.minutes_studied
            course_titles.setdefault(log.course_id, log.course.title)

        overall_planned = sum(planned_by_course.values())
        overall_completed = sum(studied_by_course.values())

        def calculate_percentage(completed, planned):
            if planned == 0:
                return 0.0
            return round((completed / planned) * 100, 2)

        courses_payload = []
        for course_id, title in course_titles.items():
            planned = planned_by_course.get(course_id, 0)
            completed = studied_by_course.get(course_id, 0)
            courses_payload.append(
                {
                    "course_id": course_id,
                    "course_title": title,
                    "planned_minutes": planned,
                    "completed_minutes": completed,
                    "completion_percentage": calculate_percentage(completed, planned),
                }
            )

        daily_planned = defaultdict(int)
        for plan in study_plans:
            daily_planned[plan.day_of_week] += plan.minutes_planned

        daily_completed = defaultdict(int)
        for log in study_logs:
            daily_completed[log.date.weekday()] += log.minutes_studied

        dias_semana = dict(StudyPlan.DayOfWeek.choices)
        daily_progress = [
            {
                "day_of_week": day_number,
                "day_name": dias_semana[day_number],
                "planned_minutes": daily_planned.get(day_number, 0),
                "completed_minutes": daily_completed.get(day_number, 0),
                "completion_percentage": calculate_percentage(
                    daily_completed.get(day_number, 0), daily_planned.get(day_number, 0)
                ),
            }
            for day_number in range(7)
        ]

        payload = {
            "week_start": start_of_week,
            "week_end": end_of_week,
            "overall": {
                "planned_minutes": overall_planned,
                "completed_minutes": overall_completed,
                "completion_percentage": calculate_percentage(
                    overall_completed, overall_planned
                ),
            },
            "courses": courses_payload,
            "daily_breakdown": daily_progress,
        }

        return Response(payload)


class StudyReminderAPIView(APIView):
    """Lista lembretes baseados nos planos de estudo da próxima semana."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        today = timezone.localdate()
        study_plans = StudyPlan.objects.filter(user=user).select_related("course")
        dias_semana = dict(StudyPlan.DayOfWeek.choices)

        reminders = []
        for plan in study_plans:
            delta = (plan.day_of_week - today.weekday()) % 7
            reminder_date = today + timedelta(days=delta)
            reminders.append(
                {
                    "plan_id": plan.id,
                    "course_id": plan.course_id,
                    "course_title": plan.course.title,
                    "scheduled_date": reminder_date,
                    "day_name": dias_semana[plan.day_of_week],
                    "minutes_planned": plan.minutes_planned,
                    "is_today": delta == 0,
                    "message": (
                        f"Estudar {plan.course.title} por {plan.minutes_planned} minutos em "
                        f"{dias_semana[plan.day_of_week]}"
                    ),
                }
            )

        reminders.sort(key=lambda item: (item["scheduled_date"], item["course_title"]))

        return Response(
            {
                "generated_at": timezone.now(),
                "reminders": reminders,
            }
        )


class StudyStatisticsAPIView(APIView):
    """Retorna estatísticas agregadas de estudo (tempo total, streaks, etc.)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        study_logs = StudyLog.objects.filter(user=user)

        total_minutes = study_logs.aggregate(total=Sum("minutes_studied"))[
            "total"
        ] or 0
        total_sessions = study_logs.count()

        distinct_dates = list(
            study_logs.order_by("date").values_list("date", flat=True).distinct()
        )
        total_active_days = len(distinct_dates)
        average_daily_minutes = (
            round(total_minutes / total_active_days, 2) if total_active_days else 0.0
        )

        # Calcula streaks
        longest_streak = 0
        current_streak = 0
        previous_date = None
        for current_date in distinct_dates:
            if previous_date and (current_date - previous_date).days == 1:
                current_streak += 1
            else:
                current_streak = 1
            longest_streak = max(longest_streak, current_streak)
            previous_date = current_date

        dates_set = set(distinct_dates)
        today = timezone.localdate()
        running_streak = 0
        cursor = today
        while cursor in dates_set:
            running_streak += 1
            cursor -= timedelta(days=1)

        top_course_raw = (
            study_logs.values("course__id", "course__title")
            .annotate(total_minutes=Sum("minutes_studied"))
            .order_by("-total_minutes")
            .first()
        )

        top_course = None
        if top_course_raw:
            top_course = {
                "course_id": top_course_raw["course__id"],
                "course_title": top_course_raw["course__title"],
                "minutes_studied": top_course_raw["total_minutes"],
            }

        payload = {
            "totals": {
                "minutes_studied": total_minutes,
                "sessions": total_sessions,
                "active_days": total_active_days,
                "average_minutes_per_active_day": average_daily_minutes,
            },
            "streaks": {
                "longest_streak": longest_streak,
                "current_streak": running_streak,
            },
            "top_course": top_course,
            "last_activity_date": distinct_dates[-1] if distinct_dates else None,
        }

        return Response(payload)
