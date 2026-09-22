from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Count
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Answer,
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    User,
)

admin.site.site_header = "ShamsQuiz Administration"
admin.site.site_title = "ShamsQuiz Admin"
admin.site.index_title = "Platform overview"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = [
        "username",
        "email",
        "role",
        "is_staff",
        "is_active",
        "last_login",
    ]
    list_filter = ["role", "is_staff", "is_active", "date_joined"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("ShamsQuiz role", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("ShamsQuiz role", {"fields": ("role",)}),
    )


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ["text", "order", "time_limit", "points"]
    show_change_link = True


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "teacher",
        "question_count",
        "live_sessions",
        "created_at",
    ]
    list_filter = ["created_at"]
    search_fields = ["title", "description", "teacher__username"]
    date_hierarchy = "created_at"
    inlines = [QuestionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _qcount=Count("questions", distinct=True),
            _sessions=Count("sessions", distinct=True),
        )

    @admin.display(description="Questions")
    def question_count(self, obj):
        url = (
            reverse("admin:quiz_question_changelist")
            + f"?module__id__exact={obj.id}"
        )
        return format_html('<a href="{}">{}</a>', url, obj._qcount)

    @admin.display(description="Live sessions")
    def live_sessions(self, obj):
        return obj._sessions


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ["text", "is_correct", "order"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = [
        "text",
        "module",
        "choice_count",
        "time_limit",
        "points",
        "order",
    ]
    list_filter = ["module", "module__teacher"]
    search_fields = ["text", "module__title"]
    list_editable = ["time_limit", "points", "order"]
    inlines = [ChoiceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_ccount=Count("choices"))

    @admin.display(description="Choices")
    def choice_count(self, obj):
        return obj._ccount


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "module",
        "host",
        "status_badge",
        "current_index",
        "players",
        "question_count",
        "created_at",
        "ended_at",
    ]
    list_filter = ["status", "created_at", "module"]
    search_fields = ["code", "module__title", "host__username"]
    ordering = ["-created_at"]
    readonly_fields = ["code", "created_at", "ended_at"]
    actions = ["action_end_quiz", "action_open_host_page"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            QuizSession.Status.WAITING: "#f59e0b",
            QuizSession.Status.QUESTION: "#6d28d9",
            QuizSession.Status.REVEAL: "#d97706",
            QuizSession.Status.ENDED: "#107c41",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:999px;font-weight:600;font-size:11px">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Players")
    def players(self, obj):
        return obj.participants.count()

    @admin.display(description="Questions")
    def question_count(self, obj):
        return obj.module.questions.count()

    @admin.action(description="End selected quizzes")
    def action_end_quiz(self, request, queryset):
        updated = queryset.exclude(status=QuizSession.Status.ENDED).update(
            status=QuizSession.Status.ENDED, ended_at=timezone.now()
        )
        self.message_user(request, f"Ended {updated} quiz session(s).")

    @admin.action(description="Open host page")
    def action_open_host_page(self, request, queryset):
        session = queryset.first()
        if session:
            url = reverse("host_control", args=[session.code])
            self.message_user(
                request,
                format_html('Open the <a href="{}">host page</a>.', url),
            )


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ["name", "session", "score", "joined_at"]
    list_filter = ["session__module"]
    search_fields = ["name", "session__code"]
    date_hierarchy = "joined_at"


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = [
        "participant",
        "question",
        "was_correct",
        "points_earned",
        "answered_at",
    ]
    list_filter = ["choice__is_correct"]
    search_fields = ["participant__name", "question__text"]

    @admin.display(description="Correct?", boolean=True)
    def was_correct(self, obj):
        return obj.choice.is_correct