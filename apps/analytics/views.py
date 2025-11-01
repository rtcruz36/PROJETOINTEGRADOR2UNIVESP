from collections import defaultdict
from datetime import timedelta

import pandas as pd
from django.db.models import Avg, Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from scipy.stats import pearsonr

from apps.assessment.models import Attempt
from apps.learning.models import Course, Topic
from apps.scheduling.models import StudyLog

from .serializers import (
    AnalyticsDashboardSerializer,
    CorrelationAnalyticsSerializer,
    EngagementMetricsSerializer,
    ScoreProgressSerializer,
    TopicComparisonSerializer,
)


def get_correlation_interpretation(coefficient):
    """Função auxiliar para traduzir o valor numérico em texto."""
    if coefficient is None or pd.isna(coefficient):
        return "Não há dados suficientes para calcular a correlação."
    
    abs_coeff = abs(coefficient)
    
    if abs_coeff >= 0.7:
        strength = "forte"
    elif abs_coeff >= 0.4:
        strength = "moderada"
    elif abs_coeff >= 0.1:
        strength = "fraca"
    else:
        return "Não há correlação significativa entre o tempo de estudo e as notas."

    direction = "positiva" if coefficient > 0 else "negativa"
    
    if direction == "positiva":
        return f"Existe uma correlação {strength} e {direction}. Isso sugere que, em geral, quanto mais tempo você estuda um tópico, melhores tendem a ser suas notas nos quizzes."
    else:
        return f"Existe uma correlação {strength} e {direction}. Isso é incomum e pode indicar que o tempo de estudo não está sendo eficaz ou que os quizzes estão avaliando outros conhecimentos."


def calculate_study_effectiveness(user):
    """Calcula a correlação entre tempo de estudo e desempenho em quizzes."""
    topics_with_study = Topic.objects.filter(
        course__user=user,
        study_logs__isnull=False,
    ).annotate(
        total_minutes_studied=Sum('study_logs__minutes_studied')
    ).distinct()

    topics_with_quiz = Topic.objects.filter(
        course__user=user,
        quizzes__isnull=False,
        quizzes__attempts__isnull=False,
    ).annotate(
        average_quiz_score=Avg('quizzes__attempts__score')
    ).distinct()

    analysis_data = []
    for topic in topics_with_study:
        quiz_data = topics_with_quiz.filter(id=topic.id).first()
        if quiz_data and topic.total_minutes_studied and quiz_data.average_quiz_score:
            analysis_data.append(
                {
                    "topic_id": topic.id,
                    "topic_title": topic.title,
                    "total_minutes_studied": topic.total_minutes_studied,
                    "average_quiz_score": round(quiz_data.average_quiz_score, 2),
                }
            )

    if len(analysis_data) < 2:
        return {
            "correlation_coefficient": None,
            "interpretation": "São necessários pelo menos dois tópicos com tempo de estudo e notas de quiz registrados para calcular a correlação.",
            "data_points": len(analysis_data),
            "topic_data": analysis_data,
        }

    df = pd.DataFrame(analysis_data)

    try:
        correlation_coefficient, _ = pearsonr(
            df["total_minutes_studied"], df["average_quiz_score"]
        )
        if pd.isna(correlation_coefficient):
            correlation_coefficient = None
    except Exception:
        correlation_coefficient = None

    return {
        "correlation_coefficient": correlation_coefficient,
        "interpretation": get_correlation_interpretation(correlation_coefficient),
        "data_points": len(df),
        "topic_data": df.to_dict("records"),
    }


def calculate_score_progression(user):
    """Analisa a evolução temporal das notas dos quizzes do usuário."""
    attempts = (
        Attempt.objects.filter(user=user, quiz__topic__course__user=user)
        .select_related("quiz__topic__course")
        .order_by("completed_at")
    )

    if not attempts.exists():
        return {
            "total_attempts": 0,
            "trend_summary": "Ainda não há tentativas suficientes para analisar a evolução das notas.",
            "timeline": [],
            "per_topic": [],
        }

    timeline_map = defaultdict(lambda: {"total": 0.0, "count": 0})
    topic_attempts = defaultdict(list)

    for attempt in attempts:
        attempt_date = attempt.completed_at.date()
        timeline_map[attempt_date]["total"] += attempt.score
        timeline_map[attempt_date]["count"] += 1
        topic_attempts[attempt.quiz.topic].append((attempt.completed_at, attempt.score))

    timeline = []
    for date_key in sorted(timeline_map.keys()):
        total = timeline_map[date_key]["total"]
        count = timeline_map[date_key]["count"]
        timeline.append(
            {
                "date": date_key,
                "average_score": round(total / count, 2),
                "attempt_count": count,
            }
        )

    first_avg = timeline[0]["average_score"]
    last_avg = timeline[-1]["average_score"]
    variation = round(last_avg - first_avg, 2)
    if abs(variation) < 1:
        trend_summary = (
            f"A média geral permaneceu estável em {last_avg:.2f}% nas últimas tentativas."
        )
    elif variation > 0:
        trend_summary = (
            f"Suas notas médias evoluíram de {first_avg:.2f}% para {last_avg:.2f}% (+{variation:.2f} pontos)."
        )
    else:
        trend_summary = (
            f"As notas médias caíram de {first_avg:.2f}% para {last_avg:.2f}% ({variation:.2f} pontos)."
        )

    per_topic = []
    for topic, entries in topic_attempts.items():
        entries.sort(key=lambda item: item[0])
        first_score = entries[0][1]
        last_score = entries[-1][1]
        score_change = round(last_score - first_score, 2) if len(entries) > 1 else 0.0
        per_topic.append(
            {
                "topic_id": topic.id,
                "topic_title": topic.title,
                "course_title": topic.course.title,
                "attempt_count": len(entries),
                "latest_score": round(last_score, 2),
                "score_change": score_change,
            }
        )

    per_topic.sort(key=lambda item: item["score_change"], reverse=True)

    return {
        "total_attempts": attempts.count(),
        "trend_summary": trend_summary,
        "timeline": timeline,
        "per_topic": per_topic,
    }


def calculate_topic_comparison(user):
    """Compara desempenho e dedicação entre tópicos e disciplinas."""
    topics = (
        Topic.objects.filter(course__user=user)
        .select_related("course")
        .order_by("course__title", "title")
    )

    study_log_totals = {
        entry["topic_id"]: entry
        for entry in StudyLog.objects.filter(user=user, topic__isnull=False)
        .values("topic_id")
        .annotate(
            total_minutes=Sum("minutes_studied"),
            session_count=Count("id"),
        )
    }

    attempt_totals = {
        entry["quiz__topic_id"]: entry
        for entry in Attempt.objects.filter(user=user, quiz__topic__course__user=user)
        .values("quiz__topic_id")
        .annotate(
            average_score=Avg("score"),
            attempt_count=Count("id"),
        )
    }

    by_topic = []
    for topic in topics:
        log_data = study_log_totals.get(topic.id, {})
        attempt_data = attempt_totals.get(topic.id, {})
        by_topic.append(
            {
                "topic_id": topic.id,
                "topic_title": topic.title,
                "course_title": topic.course.title,
                "total_minutes": int(log_data.get("total_minutes") or 0),
                "session_count": int(log_data.get("session_count") or 0),
                "average_score": (
                    round(attempt_data.get("average_score"), 2)
                    if attempt_data.get("average_score") is not None
                    else None
                ),
                "attempt_count": int(attempt_data.get("attempt_count") or 0),
            }
        )

    courses = Course.objects.filter(user=user).order_by("title")

    study_log_by_course = {
        entry["course_id"]: entry
        for entry in StudyLog.objects.filter(user=user)
        .values("course_id")
        .annotate(
            total_minutes=Sum("minutes_studied"),
            session_count=Count("id"),
        )
    }

    attempt_by_course = {
        entry["quiz__topic__course_id"]: entry
        for entry in Attempt.objects.filter(user=user, quiz__topic__course__user=user)
        .values("quiz__topic__course_id")
        .annotate(
            average_score=Avg("score"),
            attempt_count=Count("id"),
        )
    }

    by_course = []
    for course in courses:
        log_data = study_log_by_course.get(course.id, {})
        attempt_data = attempt_by_course.get(course.id, {})
        by_course.append(
            {
                "course_id": course.id,
                "course_title": course.title,
                "total_minutes": int(log_data.get("total_minutes") or 0),
                "session_count": int(log_data.get("session_count") or 0),
                "average_score": (
                    round(attempt_data.get("average_score"), 2)
                    if attempt_data.get("average_score") is not None
                    else None
                ),
                "attempt_count": int(attempt_data.get("attempt_count") or 0),
            }
        )

    if by_topic:
        best_topic = max(
            by_topic,
            key=lambda item: item["average_score"] or 0,
        )
        summary = (
            f"O tópico com melhor média de desempenho é '{best_topic['topic_title']}' "
            f"com {best_topic['average_score'] or 0:.2f}% após {best_topic['attempt_count']} tentativa(s)."
        )
    else:
        summary = "Ainda não há dados suficientes para comparar tópicos ou disciplinas."

    return {
        "by_topic": by_topic,
        "by_course": by_course,
        "summary": summary,
    }


def calculate_engagement_metrics(user):
    """Gera métricas de engajamento como streak e regularidade."""
    logs_qs = StudyLog.objects.filter(user=user).order_by("date")
    if not logs_qs.exists():
        return {
            "current_streak": 0,
            "best_streak": 0,
            "total_minutes_last_7_days": 0,
            "total_minutes_last_30_days": 0,
            "average_session_minutes": None,
            "sessions_last_7_days": 0,
            "regularity_score": 0.0,
            "most_productive_day": None,
            "weekly_minutes": [],
            "summary": "Registre novas sessões de estudo para ver métricas de engajamento.",
        }

    aggregate = logs_qs.aggregate(
        total_minutes=Sum("minutes_studied"),
        total_sessions=Count("id"),
    )
    total_minutes = aggregate["total_minutes"] or 0
    total_sessions = aggregate["total_sessions"] or 0
    average_session_minutes = (
        round(total_minutes / total_sessions, 2) if total_sessions else None
    )

    daily_data = list(
        logs_qs.values("date")
        .annotate(
            total_minutes=Sum("minutes_studied"),
            session_count=Count("id"),
        )
        .order_by("date")
    )

    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)
    twenty_eight_days_ago = today - timedelta(days=27)

    total_minutes_last_7_days = sum(
        entry["total_minutes"]
        for entry in daily_data
        if entry["date"] >= seven_days_ago
    )
    total_minutes_last_30_days = sum(
        entry["total_minutes"]
        for entry in daily_data
        if entry["date"] >= thirty_days_ago
    )
    sessions_last_7_days = sum(
        entry["session_count"]
        for entry in daily_data
        if entry["date"] >= seven_days_ago
    )

    unique_dates = [entry["date"] for entry in daily_data]
    date_set = set(unique_dates)

    current_streak = 0
    streak_day = today
    while streak_day in date_set:
        current_streak += 1
        streak_day -= timedelta(days=1)

    best_streak = 0
    temp_streak = 0
    previous_date = None
    for study_date in unique_dates:
        if previous_date and study_date == previous_date + timedelta(days=1):
            temp_streak += 1
        else:
            temp_streak = 1
        best_streak = max(best_streak, temp_streak)
        previous_date = study_date

    days_last_28 = sum(1 for d in unique_dates if d >= twenty_eight_days_ago)
    regularity_score = round((days_last_28 / 28) * 100, 2)

    weekday_labels = [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    ]
    weekday_minutes = defaultdict(int)
    for entry in daily_data:
        weekday_minutes[entry["date"].weekday()] += entry["total_minutes"]

    most_productive_day = None
    if weekday_minutes:
        best_weekday = max(weekday_minutes, key=weekday_minutes.get)
        most_productive_day = weekday_labels[best_weekday]

    weekly_minutes = []
    for week_index in range(4):
        week_end = today - timedelta(days=week_index * 7)
        week_start = week_end - timedelta(days=6)
        total = sum(
            entry["total_minutes"]
            for entry in daily_data
            if week_start <= entry["date"] <= week_end
        )
        weekly_minutes.append(
            {
                "week_start": week_start,
                "week_end": week_end,
                "total_minutes": total,
            }
        )

    weekly_minutes.sort(key=lambda item: item["week_start"])

    summary = (
        f"Você estudou {sessions_last_7_days} vez(es) nos últimos 7 dias, "
        f"acumulando {total_minutes_last_7_days} minutos. "
        f"Sequência atual: {current_streak} dia(s); melhor sequência: {best_streak} dia(s)."
    )

    return {
        "current_streak": current_streak,
        "best_streak": best_streak,
        "total_minutes_last_7_days": total_minutes_last_7_days,
        "total_minutes_last_30_days": total_minutes_last_30_days,
        "average_session_minutes": average_session_minutes,
        "sessions_last_7_days": sessions_last_7_days,
        "regularity_score": regularity_score,
        "most_productive_day": most_productive_day,
        "weekly_minutes": weekly_minutes,
        "summary": summary,
    }


class StudyEffectivenessAPIView(APIView):
    """Calcula a correlação entre minutos estudados e notas médias."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        result = calculate_study_effectiveness(request.user)
        serializer = CorrelationAnalyticsSerializer(result)
        return Response(serializer.data)


class StudyProgressAPIView(APIView):
    """Retorna a evolução temporal das notas em quizzes."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        result = calculate_score_progression(request.user)
        serializer = ScoreProgressSerializer(result)
        return Response(serializer.data)


class TopicComparisonAPIView(APIView):
    """Compara dedicação e desempenho entre tópicos e cursos."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        result = calculate_topic_comparison(request.user)
        serializer = TopicComparisonSerializer(result)
        return Response(serializer.data)


class EngagementMetricsAPIView(APIView):
    """Entrega métricas de engajamento e hábitos de estudo."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        result = calculate_engagement_metrics(request.user)
        serializer = EngagementMetricsSerializer(result)
        return Response(serializer.data)


class AnalyticsDashboardAPIView(APIView):
    """Resumo consolidado com as principais análises de estudo."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        payload = {
            "study_effectiveness": calculate_study_effectiveness(request.user),
            "score_progression": calculate_score_progression(request.user),
            "topic_comparison": calculate_topic_comparison(request.user),
            "engagement_metrics": calculate_engagement_metrics(request.user),
        }
        serializer = AnalyticsDashboardSerializer(payload)
        return Response(serializer.data)