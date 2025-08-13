# apps/analytics/serializers.py

from rest_framework import serializers

class TopicCorrelationSerializer(serializers.Serializer):
    """
    Serializa os dados de um único tópico para a análise de correlação.
    """
    topic_id = serializers.IntegerField()
    topic_title = serializers.CharField()
    total_minutes_studied = serializers.IntegerField()
    average_quiz_score = serializers.FloatField()

class CorrelationAnalyticsSerializer(serializers.Serializer):
    """
    Serializa o resultado final da análise de correlação.
    """
    correlation_coefficient = serializers.FloatField(allow_null=True, help_text="Coeficiente de correlação de Pearson (-1 a 1). Null se não for calculável.")
    interpretation = serializers.CharField(help_text="Interpretação em linguagem natural do coeficiente.")
    data_points = serializers.IntegerField(help_text="Número de tópicos com dados suficientes para o cálculo.")
    # Mostra os dados brutos que foram usados no cálculo, o que é ótimo para debug e para exibir em gráficos.
    topic_data = TopicCorrelationSerializer(many=True)

