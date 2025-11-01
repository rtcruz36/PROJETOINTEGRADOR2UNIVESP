"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView # <-- Importe as views


urlpatterns = [
    # Rotas do frontend estático
    path('', include('apps.core.urls')),

    # 1. Rota para a interface de administração do Django
    path('admin/', admin.site.urls),

    # 2. Rotas do App 'accounts' para autenticação e perfis
    # (prefixo: /api/accounts/)
    path('api/accounts/', include('apps.accounts.urls')),

    # 3. Rotas do App 'learning' para cursos, tópicos e subtópicos
    # (prefixo: /api/learning/)
    path('api/learning/', include('apps.learning.urls')),

    # 4. Rotas do App 'scheduling' para metas e geração de cronograma
    # (prefixo: /api/scheduling/)
    path('api/scheduling/', include('apps.scheduling.urls')),

    # 5. Rotas do App 'assessment' para quizzes e tentativas
    # (prefixo: /api/assessment/)
    path('api/assessment/', include('apps.assessment.urls')),

    # 6. Rota do App 'studychat' para o chat interativo com a IA
    # (prefixo: /api/chat/)
    path('api/chat/', include('apps.studychat.urls')),

    # 7. Rota do App 'analytics' para a análise de eficácia dos estudos
    # (prefixo: /api/analytics/)
    path('api/analytics/', include('apps.analytics.urls')),
    
    # URLs para a documentação da API com drf-spectacular
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'), # Gera o schema OpenAPI
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'), # Interface Swagger UI
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'), # Interface alternativa Redoc
]

# Configuração para servir arquivos de mídia (como fotos de perfil) em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

