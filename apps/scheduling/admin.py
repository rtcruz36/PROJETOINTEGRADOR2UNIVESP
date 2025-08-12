# apps/scheduling/admin.py

from django.contrib import admin
from .models import StudyPlan, StudyLog

@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'day_of_week', 'minutes_planned')
    list_filter = ('user', 'day_of_week', 'course')

@admin.register(StudyLog)
class StudyLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'topic', 'date', 'minutes_studied')
    list_filter = ('user', 'date', 'course')
    search_fields = ('notes', 'topic__title')
