from django.contrib import admin

from .models import (
    Answer,
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    User,
)

admin.site.register(User)
admin.site.register(Module)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 2


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["text", "module", "points", "time_limit", "order"]
    inlines = [ChoiceInline]


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = ["code", "module", "host", "status", "current_index"]
    list_filter = ["status"]


admin.site.register(Answer)
admin.site.register(Participant)