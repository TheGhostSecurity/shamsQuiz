import random
import string

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=200, blank=True)
    telegram = models.CharField(max_length=200, blank=True)
    facebook = models.CharField(max_length=200, blank=True)
    instagram = models.CharField(max_length=200, blank=True)
    youtube = models.CharField(max_length=200, blank=True)
    tiktok = models.CharField(max_length=200, blank=True)
    website = models.CharField(max_length=200, blank=True)

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER


class Module(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="modules"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def question_count(self):
        return self.questions.filter(is_active=True).count()


class Question(models.Model):
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField()
    time_limit = models.PositiveIntegerField(default=30, help_text="Seconds")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:60]

    def letter_choices(self):
        return list(self.choices.all())

    def save(self, *args, **kwargs):
        if self.order is None:
            self.order = 0
        if self.time_limit is None or self.time_limit < 10:
            self.time_limit = 10
        if not self.pk and self.order == 0:
            last = (
                Question.objects.filter(module=self.module)
                .order_by("-order")
                .first()
            )
            self.order = (last.order + 1) if last else 1
        super().save(*args, **kwargs)


class BankQuestion(models.Model):
    text = models.TextField()
    subject = models.CharField(max_length=100, blank=True)
    time_limit = models.PositiveIntegerField(default=30, help_text="Seconds")
    is_active = models.BooleanField(default=True)
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_questions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Bank questions"

    def __str__(self):
        return self.text[:60]


class BankChoice(models.Model):
    question = models.ForeignKey(
        BankQuestion, on_delete=models.CASCADE, related_name="choices"
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="choices"
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    @property
    def letter(self):
        choices = list(self.question.choices.all())
        if self in choices:
            return chr(65 + choices.index(self))
        return "?"

    def __str__(self):
        return self.text


class QuizSession(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        QUESTION = "question", "Question active"
        REVEAL = "reveal", "Revealing answer"
        ENDED = "ended", "Ended"

    code = models.CharField(max_length=6, unique=True, editable=False)
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, related_name="sessions"
    )
    host = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="hosted_sessions"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.WAITING
    )
    current_index = models.PositiveIntegerField(default=0)
    question_started_at = models.DateTimeField(null=True, blank=True)
    question_ends_at = models.DateTimeField(null=True, blank=True)
    question_pause_remaining = models.PositiveIntegerField(default=0)
    teams_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} · {self.module.title}"

    @staticmethod
    def generate_code():
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not QuizSession.objects.filter(code=code).exists():
                return code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    @property
    def questions(self):
        return list(self.module.questions.filter(is_active=True))

    @property
    def question_count(self):
        return self.module.questions.filter(is_active=True).count()

    @property
    def current_question(self):
        qs = list(self.module.questions.filter(is_active=True))
        if not qs:
            return None
        if self.current_index >= len(qs):
            return None
        return qs[self.current_index]

    def is_accepting_answers(self):
        now = timezone.now()
        return (
            self.status == self.Status.QUESTION
            and self.question_ends_at is not None
            and now < self.question_ends_at
        )

    @property
    def is_paused(self):
        return (
            self.status == self.Status.QUESTION
            and self.question_ends_at is None
            and self.question_pause_remaining > 0
        )

    def pause(self):
        if self.status != self.Status.QUESTION or self.question_ends_at is None:
            return
        self.question_pause_remaining = max(
            0, int((self.question_ends_at - timezone.now()).total_seconds())
        )
        self.question_ends_at = None
        self.save(update_fields=["question_ends_at", "question_pause_remaining"])

    def resume(self):
        if not self.is_paused:
            return
        self.question_ends_at = timezone.now() + timezone.timedelta(
            seconds=self.question_pause_remaining
        )
        self.question_pause_remaining = 0
        self.save(update_fields=["question_ends_at", "question_pause_remaining"])

    def add_time(self, seconds=15):
        if self.status != self.Status.QUESTION or self.question_ends_at is None:
            return
        self.question_ends_at = self.question_ends_at + timezone.timedelta(
            seconds=seconds
        )
        self.save(update_fields=["question_ends_at"])

    def seconds_remaining(self):
        now = timezone.now()
        if self.question_ends_at is None:
            return 0
        return max(0, int((self.question_ends_at - now).total_seconds()))


class Participant(models.Model):
    class Team(models.TextChoices):
        RED = "red", "Red"
        BLUE = "blue", "Blue"
        YELLOW = "yellow", "Yellow"
        GREEN = "green", "Green"

    session = models.ForeignKey(
        QuizSession, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="participations",
        help_text="Student account this play is linked to (progress tracking).",
    )
    name = models.CharField(max_length=100)
    team = models.CharField(
        max_length=10, choices=Team.choices, blank=True, default=""
    )
    score = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "name"],
                name="uniq_session_participant_name",
            )
        ]

    def __str__(self):
        return self.name


class Answer(models.Model):
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice = models.ForeignKey(Choice, on_delete=models.CASCADE)
    points_earned = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "question"],
                name="uniq_participant_question",
            )
        ]

    def __str__(self):
        return f"{self.participant.name} → {self.question}"


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        SIGNUP = "signup", "Signup"
        MODULE_CREATED = "module_created", "Module created"
        MODULE_DELETED = "module_deleted", "Module deleted"
        QUIZ_HOSTED = "quiz_hosted", "Quiz hosted"
        QUIZ_ENDED = "quiz_ended", "Quiz ended"
        QUIZ_JOINED = "quiz_joined", "Quiz joined"
        USER_CREATED = "user_created", "User created"
        USER_UPDATED = "user_updated", "User updated"
        USER_DELETED = "user_deleted", "User deleted"
        SESSION_ENDED = "session_ended", "Session ended"
        REPORT_DOWNLOADED = "report_downloaded", "Report downloaded"
        BANK_ADDED = "bank_added", "Bank question imported"
        QUESTION_BANKED = "question_banked", "Question saved to bank"
        PROFILE_UPDATED = "profile_updated", "Profile updated"
        PASSWORD_CHANGED = "password_changed", "Password changed"

    actor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="activity_logs"
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    target = models.CharField(max_length=200, blank=True)
    details = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.actor} · {self.action} · {self.created_at:%Y-%m-%d %H:%M}"


def log_activity(actor, action, target="", details=""):
    ActivityLog.objects.create(
        actor=actor, action=action, target=target, details=details
    )