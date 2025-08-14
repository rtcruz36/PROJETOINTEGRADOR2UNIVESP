from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
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
        # Atribuir o usuário autenticado como um atributo de instância
        self.user = request.user

        # 1. Calcular agregações separadamente para evitar JOINs múltiplos
        topics_with_study = Topic.objects.filter(
            course__user=self.user,
            study_logs__isnull=False
        ).annotate(
            total_minutes_studied=Sum('study_logs__minutes_studied')
        ).distinct()

        topics_with_quiz = Topic.objects.filter(
            course__user=self.user,
            quizzes__isnull=False,
            quizzes__attempts__isnull=False  # Garante que haja tentativas registradas
        ).annotate(
            average_quiz_score=Avg('quizzes__attempts__score')  # Calcula a média das pontuações das tentativas
        ).distinct()

        # 2. Combinar os dados manualmente
        analysis_data = []
        for topic in topics_with_study:
            # Encontrar dados de quiz para este tópico - CORREÇÃO AQUI
            quiz_data = topics_with_quiz.filter(id=topic.id).first()
            if quiz_data and topic.total_minutes_studied and quiz_data.average_quiz_score:
                analysis_data.append({
                    "topic_id": topic.id,
                    "topic_title": topic.title,
                    "total_minutes_studied": topic.total_minutes_studied,
                    "average_quiz_score": round(quiz_data.average_quiz_score, 2)
                })

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
        
        try:
            correlation_coefficient, _ = pearsonr(df['total_minutes_studied'], df['average_quiz_score'])
            if pd.isna(correlation_coefficient):
                correlation_coefficient = None
        except Exception:
            correlation_coefficient = None

        # 4. Montar a resposta final
        result = {
            "correlation_coefficient": correlation_coefficient,
            "interpretation": get_correlation_interpretation(correlation_coefficient),
            "data_points": len(df),
            "topic_data": df.to_dict('records')
        }

        serializer = CorrelationAnalyticsSerializer(result)
        return Response(serializer.data)