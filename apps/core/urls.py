"""URL configuration for the static frontend pages."""

from django.conf import settings
from django.urls import path, re_path
from django.views.generic import TemplateView
from django.views.static import serve as static_serve

frontend_templates = {
    '': 'index.html',
    'index.html': 'index.html',
    'analytics.html': 'analytics.html',
    'planner.html': 'planner.html',
    'profile.html': 'profile.html',
    'quiz.html': 'quiz.html',
    'quiz-results.html': 'quiz-results.html',
    'quizzes.html': 'quizzes.html',
    'schedule.html': 'schedule.html',
    'study-log.html': 'study-log.html',
    'study.html': 'study.html',
    'studybot.html': 'studybot.html',
}

app_name = 'core'

urlpatterns = [
    path(
        url_path,
        TemplateView.as_view(template_name=template),
        name=f"frontend-{template.split('.')[0].replace('-', '_')}",
    )
    for url_path, template in frontend_templates.items()
]

urlpatterns += [
    re_path(r'^styles/(?P<path>.*)$', static_serve, {'document_root': settings.BASE_DIR / 'frontend' / 'styles'}),
    re_path(r'^js/(?P<path>.*)$', static_serve, {'document_root': settings.BASE_DIR / 'frontend' / 'js'}),
]
