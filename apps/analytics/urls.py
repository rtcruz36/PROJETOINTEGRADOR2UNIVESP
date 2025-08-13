# apps/analytics/urls.py

from django.urls import path
from .views import StudyEffectivenessAPIView

urlpatterns = [
    # Endpoint único para a análise de eficácia do estudo
    path('study-effectiveness/', StudyEffectivenessAPIView.as_view(), name='analytics-study-effectiveness'),
]
