# apps/learning/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LearningCreationAPIView,
    CourseViewSet,
    TopicViewSet,
    SubtopicUpdateAPIView
)

# O router cuida das URLs para os ViewSets (que são de leitura)
router = DefaultRouter()
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'topics', TopicViewSet, basename='topic')

urlpatterns = [
    # Endpoint principal para criar o plano de estudos
    path('create-study-plan/', LearningCreationAPIView.as_view(), name='create-study-plan'),
    
    # Endpoint para marcar um subtópico como concluído
    path('subtopics/<int:pk>/', SubtopicUpdateAPIView.as_view(), name='subtopic-update'),
    
    # Inclui as URLs geradas pelo router (para listar cursos e tópicos)
    path('', include(router.urls)),
]
