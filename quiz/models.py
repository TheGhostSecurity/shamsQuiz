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
        return self.questions.count()


class Question(models.Model):
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField()
    time_limit = models.PositiveIntegerField(default=30, help_text="Seconds")
    points = models.PositiveIntegerField(default=1000)
    order = models.PositiveIntegerField(default=0)
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
        if not self.pk and self.order == 0:
            last = (
                Question.objects.filter(module=self.module)
                .order_by("-order")
                .first()
            )
            self.order = (last.order + 1) if last else 1
        super().save(*args, **kwargs)


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="choices"
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

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
        return list(self.module.questions.all())

    @property
    def question_count(self):
        return self.module.questions.count()

    @property
    def current_question(self):
        qs = list(self.module.questions.all())
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

    def seconds_remaining(self):
        now = timezone.now()
        if self.question_ends_at is None:
            return 0
        return max(0, int((self.question_ends_at - now).total_seconds()))


class Participant(models.Model):
    session = models.ForeignKey(
        QuizSession, on_delete=models.CASCADE, related_name="participants"
    )
    name = models.CharField(max_length=100)
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