"""Web/mobile realtime sync calibration.

The Android app holds a WebSocket open during live play, while the web UI polls
``/api/quiz/<code>/state/``. These tests assert that teacher actions taken
through the ordinary web views are broadcast to the mobile channel group, so
both surfaces converge without the app needing to reconnect.

Run with:  python manage.py test quiz.tests_sync_web_mobile
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Answer, Choice, Module, Participant, Question, QuizSession

User = get_user_model()


def collect_broadcasts():
    """Replace the channel layer with an in-memory spy that records sends."""
    events = []

    class SpyLayer:
        async def group_send(self, group, message):
            events.append((group, message))

        async def send(self, channel, message):  # pragma: no cover
            events.append((channel, message))

    layer = SpyLayer()
    return layer, events


class WebMobileSyncTests(TestCase):
    """Teacher web actions must reach the mobile WebSocket group."""

    def setUp(self):
        self.layer, self.events = collect_broadcasts()
        self.layer_patcher = patch(
            "mobileapi.broadcast.get_channel_layer", return_value=self.layer
        )
        self.layer_patcher.start()
        self.addCleanup(self.layer_patcher.stop)

        self.teacher = User.objects.create_user(
            username="teacher1", password="pw-teacher-123", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="student1", password="pw-student-123", role=User.Role.STUDENT
        )

        self.module = Module.objects.create(
            title="Sync Module", teacher=self.teacher, description="sync test"
        )
        self.question = Question.objects.create(
            module=self.module, text="What is 2 + 2?", time_limit=30,
            order=1, is_active=True,
        )
        self.correct = Choice.objects.create(
            question=self.question, text="4", is_correct=True, order=1
        )
        self.wrong = Choice.objects.create(
            question=self.question, text="3", is_correct=False, order=2
        )

        self.session = QuizSession.objects.create(
            module=self.module, host=self.teacher, teams_enabled=False
        )
        self.code = self.session.code
        self.participant = Participant.objects.create(
            session=self.session, user=self.student, name="MobileStudent"
        )

    def _host_post(self, name):
        return self.client.post(reverse(name, args=[self.code]), follow=True)

    def _login_teacher(self):
        self.client.force_login(self.teacher)

    def _events(self, event=None):
        out = []
        for group, message in self.events:
            payload = message.get("payload", {})
            if event is None or payload.get("event") == event:
                out.append((group, payload))
        return out

    # -- the group name must match the mobile consumer's group ---------------
    def test_broadcast_targets_the_mobile_group(self):
        from mobileapi.broadcast import group_for

        self.assertEqual(group_for(self.code), f"quiz.{self.code}")

    def test_start_question_broadcasts_state(self):
        self._login_teacher()
        self._host_post("host_start_question")

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, QuizSession.Status.QUESTION)

        state_events = self._events("state")
        self.assertTrue(state_events, "teacher start must broadcast a state push")
        group, payload = state_events[-1]
        self.assertEqual(group, f"quiz.{self.code}")
        self.assertEqual(payload["state"]["status"], QuizSession.Status.QUESTION)

    def test_reveal_broadcasts_state(self):
        self._login_teacher()
        self._host_post("host_start_question")
        self._host_post("host_reveal")

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, QuizSession.Status.REVEAL)

        states = [p["state"]["status"] for _, p in self._events("state")]
        self.assertIn(QuizSession.Status.REVEAL, states)
        self.assertIn("reveal", [p.get("event") for _, p in self._events()])

    def test_next_question_broadcasts_state(self):
        Question.objects.create(
            module=self.module, text="Second question", time_limit=30,
            order=2, is_active=True,
        )
        self._login_teacher()
        self._host_post("host_start_question")
        self._host_post("host_next_question")

        self.session.refresh_from_db()
        self.assertEqual(self.session.current_index, 1)
        states = [p["state"]["current_index"] for _, p in self._events("state")]
        self.assertIn(1, states)

    def test_pause_and_resume_broadcast(self):
        self._login_teacher()
        self._host_post("host_start_question")
        self._host_post("host_pause")
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_paused)

        self._host_post("host_resume")
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_paused)

        names = [p.get("event") for _, p in self._events()]
        self.assertIn("paused", names)
        self.assertIn("resumed", names)

    def test_end_quiz_broadcasts_ended(self):
        self._login_teacher()
        self._host_post("host_start_question")
        self._host_post("host_end_quiz")

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, QuizSession.Status.ENDED)
        states = [p["state"]["status"] for _, p in self._events("state")]
        self.assertIn(QuizSession.Status.ENDED, states)

    def test_web_state_endpoint_agrees_with_broadcast(self):
        """The polled payload and the pushed payload must not disagree."""
        self._login_teacher()
        self._host_post("host_start_question")

        pushed = self._events("state")[-1][1]["state"]

        polled = self.client.get(reverse("quiz_state", args=[self.code])).json()

        self.assertEqual(pushed["status"], polled["status"])
        self.assertEqual(pushed["code"], polled["code"])
        self.assertEqual(
            pushed["question"]["text"], polled["question"]["text"]
        )

    def test_mobile_answer_reaches_the_teacher_web_view(self):
        """An answer submitted by the app is reflected in the shared DB."""
        self._login_teacher()
        self._host_post("host_start_question")

        Answer.objects.create(
            participant=self.participant, question=self.question,
            choice=self.correct, points_earned=1,
        )

        polled = self.client.get(reverse("quiz_state", args=[self.code])).json()
        self.assertEqual(polled["answered_count"], 1)

        self.assertEqual(
            Answer.objects.filter(participant=self.participant).count(), 1
        )

    def test_broadcast_failure_never_breaks_teacher_action(self):
        """A notification error must not roll back or 500 the host action."""
        with patch(
            "mobileapi.broadcast.broadcast_state", side_effect=RuntimeError("redis down")
        ):
            self._login_teacher()
            response = self._host_post("host_start_question")

        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, QuizSession.Status.QUESTION)


class MobileConsumerGroupTests(TestCase):
    """The consumer must join exactly the group the web views broadcast to."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="host", password="pw-host-123", role=User.Role.TEACHER
        )
        self.module = Module.objects.create(
            title="M", teacher=self.teacher, description="d"
        )
        Question.objects.create(
            module=self.module, text="q", time_limit=30, order=1, is_active=True
        )
        self.session = QuizSession.objects.create(
            module=self.module, host=self.teacher
        )

    def test_consumer_group_matches_broadcast_group(self):
        """The consumer must join the same group name the web views send to.

        This is the contract that makes web -> mobile push work; if either side
        renames the group, sync silently breaks, so assert the literal strings.
        """
        from mobileapi.broadcast import group_for

        code = self.session.code
        self.assertEqual(group_for(code), f"quiz.{code}")
        # The consumer upper-cases the URL segment; group_for must normalise so
        # a lowercase join cannot land in a different group than the web views.
        self.assertEqual(group_for(code), group_for(code.lower()))
