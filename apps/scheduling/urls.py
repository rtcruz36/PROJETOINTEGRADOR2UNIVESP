# apps/scheduling/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StudyPlanViewSet, GenerateScheduleAPIView, StudyLogViewSet

router = DefaultRouter()
router.register(r'plans', StudyPlanViewSet, basename='studyplan')
router.register(r'logs', StudyLogViewSet, basename='studylog')

urlpatterns = [
    # Endpoint principal para gerar o cronograma distribuído
    path('generate-schedule/', GenerateScheduleAPIView.as_view(), name='generate-schedule'),
    
    # Inclui as URLs para gerenciar Planos e Logs (CRUD)
    path('', include(router.urls)),
]
