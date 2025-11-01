# apps/scheduling/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CurrentWeekScheduleAPIView,
    GenerateScheduleAPIView,
    StudyLogViewSet,
    StudyPlanViewSet,
    StudyReminderAPIView,
    StudyStatisticsAPIView,
    WeeklyProgressAPIView,
)

router = DefaultRouter()
router.register(r'plans', StudyPlanViewSet, basename='studyplan')
router.register(r'logs', StudyLogViewSet, basename='studylog')

urlpatterns = [
    # Endpoint principal para gerar o cronograma distribuído
    path('generate-schedule/', GenerateScheduleAPIView.as_view(), name='generate-schedule'),
    path('current-week/', CurrentWeekScheduleAPIView.as_view(), name='current-week-schedule'),
    path('progress/', WeeklyProgressAPIView.as_view(), name='weekly-progress'),
    path('reminders/', StudyReminderAPIView.as_view(), name='study-reminders'),
    path('statistics/', StudyStatisticsAPIView.as_view(), name='study-statistics'),

    # Inclui as URLs para gerenciar Planos e Logs (CRUD)
    path('', include(router.urls)),
]
