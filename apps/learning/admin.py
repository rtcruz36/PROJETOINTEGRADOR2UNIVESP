# apps/learning/admin.py

from django.contrib import admin
from .models import Course, Topic, Subtopic

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at')
    search_fields = ('title', 'description')
    list_filter = ('user',)

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'created_at')
    search_fields = ('title',)
    list_filter = ('course__user', 'course')
    # Preenche o slug automaticamente a partir do título (muito útil!)
    prepopulated_fields = {'slug': ('title',)}

@admin.register(Subtopic)
class SubtopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'order', 'is_completed')
    search_fields = ('title',)
    list_filter = ('topic__course', 'is_completed')
    list_editable = ('is_completed', 'order')
