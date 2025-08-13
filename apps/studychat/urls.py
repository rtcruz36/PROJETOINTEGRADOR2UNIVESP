# apps/studychat/urls.py

from django.urls import path
from .views import StudyChatAPIView

urlpatterns = [
    # Endpoint único para fazer perguntas ao StudyBot
    path('ask/', StudyChatAPIView.as_view(), name='studychat-ask'),
]
