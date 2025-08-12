# apps/assessment/admin.py

from django.contrib import admin
from .models import Quiz, Question, Attempt, Answer

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0 # Não mostra perguntas extras em branco para adicionar

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'total_questions', 'created_at')
    list_filter = ('topic__course__user', 'topic')
    inlines = [QuestionInline] # Mostra as perguntas dentro da página do Quiz

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ('question', 'user_answer', 'is_correct') # Apenas para visualização

@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'score', 'completed_at')
    list_filter = ('user', 'quiz')
    inlines = [AnswerInline] # Mostra as respostas do usuário dentro da página da tentativa
