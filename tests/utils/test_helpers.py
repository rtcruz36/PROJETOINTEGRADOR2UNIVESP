# tests/utils/test_helpers.py
"""
Utilitários auxiliares para testes.
"""
from datetime import date
from django.contrib.auth import get_user_model
from apps.learning.models import Course, Topic, Subtopic

User = get_user_model()

class TestDataFactory:
    """Factory para criar dados de teste."""
    
    @staticmethod
    def create_simple_user():
        """Cria um usuário simples para testes."""
        return User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )