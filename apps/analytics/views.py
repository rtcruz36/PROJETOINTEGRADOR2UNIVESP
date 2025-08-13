# apps/analytics/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Sum, Avg

import pandas as pd
from scipy.stats import pearsonr

from apps.learning.models import Topic
from .serializers import CorrelationAnalyticsSerializer

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


class StudyEffectivenessAPIView(APIView):
    """
    Endpoint de análise que calcula a correlação entre o tempo de estudo
    por tópico e as notas médias dos quizzes para esses tópicos.
    URL: GET /api/analytics/study-effectiveness/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        # 1. Buscar todos os tópicos do usuário que têm tanto registros de estudo quanto tentativas de quiz.
        # Usamos anotações para pré-calcular os agregados no banco de dados, o que é muito eficiente.
        topics_with_data = Topic.objects.filter(
            course__user=user,
            study_logs__isnull=False,  # Garante que há pelo menos um log de estudo
            quizzes__attempts__isnull=False # Garante que há pelo menos uma tentativa de quiz
        ).annotate(
            total_minutes_studied=Sum('study_logs__minutes_studied'),
            average_quiz_score=Avg('quizzes__attempts__score')
        ).distinct() # distinct() é importante por causa dos joins múltiplos

        # 2. Preparar os dados para a análise
        # Filtramos tópicos onde os dados agregados não são nulos
        analysis_data = [
            {
                "topic_id": topic.id,
                "topic_title": topic.title,
                "total_minutes_studied": topic.total_minutes_studied,
                "average_quiz_score": round(topic.average_quiz_score, 2)
            }
            for topic in topics_with_data if topic.total_minutes_studied is not None and topic.average_quiz_score is not None
        ]

        # Se não tivermos pelo menos 2 pontos de dados, não podemos calcular a correlação
        if len(analysis_data) < 2:
            result = {
                "correlation_coefficient": None,
                "interpretation": "São necessários pelo menos dois tópicos com tempo de estudo e notas de quiz registrados para calcular a correlação.",
                "data_points": len(analysis_data),
                "topic_data": analysis_data
            }
            serializer = CorrelationAnalyticsSerializer(result)
            return Response(serializer.data)

        # 3. Usar Pandas e SciPy para o cálculo
        df = pd.DataFrame(analysis_data)
        
        # pearsonr retorna (coeficiente, p-valor). Só precisamos do coeficiente.
        # O p-valor seria útil para análises estatísticas mais rigorosas.
        try:
            correlation_coefficient, _ = pearsonr(df['total_minutes_studied'], df['average_quiz_score'])
            # Se o resultado for NaN (Not a Number), o que pode acontecer se todos os valores forem iguais, tratamos como nulo.
            if pd.isna(correlation_coefficient):
                correlation_coefficient = None
        except Exception:
            correlation_coefficient = None

        # 4. Montar a resposta final
        result = {
            "correlation_coefficient": correlation_coefficient,
            "interpretation": get_correlation_interpretation(correlation_coefficient),
            "data_points": len(df),
            "topic_data": df.to_dict('records') # Converte o DataFrame de volta para uma lista de dicionários
        }

        serializer = CorrelationAnalyticsSerializer(result)
        return Response(serializer.data, status=status.HTTP_200_OK)

