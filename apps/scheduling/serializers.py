# apps/scheduling/serializers.py

from rest_framework import serializers
from .models import StudyPlan, StudyLog
from apps.learning.models import Topic, Course

class StudyPlanSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo StudyPlan (Metas de Estudo).
    """
    # Usamos o nome do dia da semana para facilitar a leitura no frontend
    day_of_week_display = serializers.CharField(source='get_day_of_week_display', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = StudyPlan
        fields = [
            'id', 
            'course', 
            'course_title',
            'day_of_week', 
            'day_of_week_display', 
            'minutes_planned'
        ]
        # O usuário é pego do contexto, não enviado no JSON
        read_only_fields = ['id']

    def validate(self, data):
        """
        Validação para garantir que o usuário não crie planos para cursos de outros.
        """
        course = data.get('course')
        user = self.context['request'].user
        if course and course.user != user:
            raise serializers.ValidationError("Você só pode criar planos de estudo para suas próprias disciplinas.")
        return data

class StudyLogSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo StudyLog (Sessões de Estudo Realizadas).
    """
    class Meta:
        model = StudyLog
        fields = [
            'id', 
            'topic', 
            'course', 
            'date', 
            'minutes_studied', 
            'notes', 
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        """
        Validação para garantir que o log pertence a um curso do usuário.
        """
        course = data.get('course')
        user = self.context['request'].user
        if course and course.user != user:
            raise serializers.ValidationError("Você só pode registrar estudos para suas próprias disciplinas.")
        return data

