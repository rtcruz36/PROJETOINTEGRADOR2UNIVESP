# apps/learning/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CourseViewSet,
    LearningCreationAPIView,
    SubtopicReorderAPIView,
    SubtopicUpdateAPIView,
    SubtopicViewSet,
    TopicReorderAPIView,
    TopicViewSet,
)

router = DefaultRouter()
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'subtopics', SubtopicViewSet, basename='subtopic')

urlpatterns = [
    path('create-study-plan/', LearningCreationAPIView.as_view(), name='create-study-plan'),
    path('subtopics/<int:pk>/', SubtopicUpdateAPIView.as_view(), name='subtopic-update'),
    path('courses/<int:course_pk>/reorder-topics/', TopicReorderAPIView.as_view(), name='course-reorder-topics'),
    path('topics/<int:topic_pk>/reorder-subtopics/', SubtopicReorderAPIView.as_view(), name='topic-reorder-subtopics'),
    path('', include(router.urls)),
]
