# apps/assessment/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GenerateQuizView,
    SubmitAttemptAPIView,
    QuizViewSet,
    AttemptViewSet
)

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet, basename='quiz')
router.register(r'attempts', AttemptViewSet, basename='attempt')

urlpatterns = [
    path('generate-quiz/', GenerateQuizView.as_view(), name='generate-quiz'),
    path('submit-attempt/', SubmitAttemptAPIView.as_view(), name='submit-attempt'),
    path('', include(router.urls)),
]
