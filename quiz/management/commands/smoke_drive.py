"""Drive a quiz session's teacher controls from the command line.

Used by the Flutter live smoke test to simulate a teacher running the quiz,
so no dev-only HTTP bypass has to be added to the backend.

Usage:
    python manage.py smoke_drive start TQ2VZH
    python manage.py smoke_drive reveal TQ2VZH
    python manage.py smoke_drive end TQ2VZH
    python manage.py smoke_drive status TQ2VZH
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from quiz.models import QuizSession


class Command(BaseCommand):
    help = "Advance a quiz session so the mobile app smoke test can play it."

    def add_arguments(self, parser):
        parser.add_argument("action")
        parser.add_argument("code")
        parser.add_argument(
            "--seconds",
            type=int,
            default=None,
            help="Override the question time limit for this run.",
        )

    def handle(self, *args, **options):
        action = options["action"].strip().lower()
        code = options["code"].strip().upper()

        session = QuizSession.objects.filter(code=code).first()
        if session is None:
            raise CommandError(f"No quiz found with code {code}")

        now = timezone.now()
        question = session.current_question
        limit = options["seconds"] or (question.time_limit if question else 30)

        if action == "start":
            session.status = QuizSession.Status.QUESTION
            session.current_index = 0
            session.question_started_at = now
            session.question_ends_at = now + timezone.timedelta(seconds=limit)
            session.question_pause_remaining = 0
        elif action == "reveal":
            session.status = QuizSession.Status.REVEAL
            session.question_ends_at = None
            session.question_pause_remaining = 0
        elif action == "next":
            session.current_index += 1
            session.status = QuizSession.Status.QUESTION
            session.question_started_at = now
            session.question_ends_at = now + timezone.timedelta(seconds=limit)
            session.question_pause_remaining = 0
        elif action == "end":
            session.status = QuizSession.Status.ENDED
            session.question_ends_at = None
            session.ended_at = now
        elif action == "pause":
            session.save()
            session.pause()
        elif action == "resume":
            session.save()
            session.resume()
        elif action != "status":
            raise CommandError(f"Unknown action: {action}")

        session.save()

        out = self.stdout
        out.write(f"ACTION={action}")
        out.write(f"CODE={session.code}")
        out.write(f"STATUS={session.status}")
        out.write(f"INDEX={session.current_index}")
        out.write(f"PAUSED={session.is_paused}")
        out.write(f"REMAINING={session.seconds_remaining()}")
        current = session.current_question
        if current is not None:
            out.write(f"QUESTION_ID={current.id}")
            out.write(f"QUESTION_TEXT={current.text}")
            for choice in current.choices.all().order_by("order", "id"):
                out.write(f"CHOICE={choice.id}|{choice.text}|{choice.is_correct}")
