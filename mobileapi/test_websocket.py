from datetime import timedelta

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from quiz.models import (
    Choice,
    Module,
    Participant,
    Question,
    QuizSession,
    User,
)

from .permissions import hash_ticket

STRONG_PW = "Quizpass123!"


def make_teacher():
    return User.objects.create_user(
        username="teacher1", password=STRONG_PW, role="teacher"
    )


def make_student(username="amina"):
    return User.objects.create_user(
        username=username, password=STRONG_PW, role="student"
    )


def make_session(teacher, status=QuizSession.Status.WAITING, teams=False):
    module = Module.objects.create(title="Module X", teacher=teacher)
    for i in range(2):
        question = Question.objects.create(
            module=module, text=f"Question {i + 1}", time_limit=30
        )
        Choice.objects.create(question=question, text="Right", is_correct=True, order=1)
        Choice.objects.create(question=question, text="Wrong A", order=2)
        Choice.objects.create(question=question, text="Wrong B", order=3)
    return QuizSession.objects.create(
        module=module, host=teacher, status=status, teams_enabled=teams
    )


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class QuizWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.session = make_session(self.teacher)

    def url(self, code=None):
        return f"/ws/quiz/{code or self.session.code}/"

    async def connect(self, code=None, ticket=None):
        url = self.url(code)
        if ticket:
            url = f"{url}?ticket={ticket}"
        communicator = WebsocketCommunicator(application=self.application(), path=url)
        connected, _ = await communicator.connect(timeout=5)
        return communicator, connected

    def application(self):
        from shamsquiz.asgi import application

        return application

    async def recv_event(self, communicator, wanted="state"):
        for _ in range(12):
            payload = await communicator.receive_json_from(timeout=5)
            if payload.get("event") == wanted:
                return payload
        raise AssertionError(f"never received {wanted}")

    @database_sync_to_async
    def start_question(self):
        session = QuizSession.objects.get(pk=self.session.pk)
        session.status = QuizSession.Status.QUESTION
        session.current_index = 0
        session.question_started_at = timezone.now()
        session.question_ends_at = timezone.now() + timedelta(seconds=30)
        session.save()
        return session

    @database_sync_to_async
    def get_participant(self, name):
        return Participant.objects.get(session=self.session, name=name)

    @database_sync_to_async
    def participant_count(self):
        return Participant.objects.filter(session=self.session).count()

    @database_sync_to_async
    def first_choice_id(self, correct):
        return (
            self.session.current_question.choices.filter(is_correct=correct)
            .first()
            .id
        )

    async def test_connect_unknown_code_closes(self):
        communicator, connected = await self.connect(code="ZZZ999")
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_connect_sends_state(self):
        communicator, connected = await self.connect()
        self.assertTrue(connected)
        payload = await self.recv_event(communicator, "state")
        self.assertEqual(payload["state"]["code"], self.session.code)
        self.assertEqual(payload["state"]["status"], QuizSession.Status.WAITING)
        await communicator.disconnect()

    async def test_join_returns_ticket_and_creates_participant(self):
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})

        ticket = None
        state = None
        for _ in range(12):
            payload = await communicator.receive_json_from(timeout=5)
            if payload.get("event") == "ticket":
                ticket = payload["ticket"]
            if payload.get("event") == "state" and state is None:
                state = payload["state"]
        self.assertIsNotNone(ticket)
        self.assertIsNotNone(state)
        self.assertIsNotNone(state["participant"])
        self.assertEqual(state["participant"]["name"], "Amina")
        self.assertEqual(await self.participant_count(), 1)
        await communicator.disconnect()

    async def test_join_short_name_rejected(self):
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "A"})
        payload = await self.recv_event(communicator, "error")
        self.assertIn("2 characters", payload["error"])
        await communicator.disconnect()

    async def test_join_duplicate_name_rejected(self):
        await Participant.objects.acreate(session=self.session, name="Amina")
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        payload = await self.recv_event(communicator, "error")
        self.assertIn("taken", payload["error"])
        await communicator.disconnect()

    async def test_join_requires_team_when_teams_enabled(self):
        session = await self._set_teams(True)
        communicator, _ = await self.connect(code=session.code)
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        payload = await self.recv_event(communicator, "error")
        self.assertIn("team", payload["error"].lower())
        await communicator.disconnect()

    async def test_join_with_team_succeeds(self):
        session = await self._set_teams(True)
        communicator, _ = await self.connect(code=session.code)
        await self.recv_event(communicator, "state")
        await communicator.send_json_to(
            {"action": "join", "nickname": "Amina", "team": "blue"}
        )
        payload = await self.recv_event(communicator, "ticket")
        self.assertTrue(payload["ticket"])
        await communicator.disconnect()

    async def test_answer_before_join_rejected(self):
        await self.start_question()
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "answer", "choice_id": 1})
        payload = await self.recv_event(communicator, "error")
        self.assertIn("Join", payload["error"])
        await communicator.disconnect()

    async def test_correct_answer_returns_points_and_leaderboard(self):
        await self.start_question()
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(communicator, "ticket")

        choice_id = await self.first_choice_id(True)
        await communicator.send_json_to(
            {"action": "answer", "choice_id": choice_id}
        )
        answered = await self.recv_event(communicator, "answered")
        self.assertTrue(answered["result"]["correct"])
        self.assertGreater(answered["result"]["points"], 900)

        board = await self.recv_event(communicator, "leaderboard")
        self.assertEqual(board["leaderboard"][0]["name"], "Amina")
        await communicator.disconnect()

    async def test_wrong_answer_scores_zero(self):
        await self.start_question()
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(communicator, "ticket")

        choice_id = await self.first_choice_id(False)
        await communicator.send_json_to(
            {"action": "answer", "choice_id": choice_id}
        )
        answered = await self.recv_event(communicator, "answered")
        self.assertFalse(answered["result"]["correct"])
        self.assertEqual(answered["result"]["points"], 0)
        await communicator.disconnect()

    async def test_double_answer_rejected(self):
        await self.start_question()
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(communicator, "ticket")

        choice_id = await self.first_choice_id(True)
        await communicator.send_json_to(
            {"action": "answer", "choice_id": choice_id}
        )
        await self.recv_event(communicator, "answered")
        await communicator.send_json_to(
            {"action": "answer", "choice_id": choice_id}
        )
        rejected = await self.recv_event(communicator, "answer_rejected")
        self.assertIn("already", rejected["error"].lower())
        await communicator.disconnect()

    async def test_answer_after_reveal_rejected(self):
        session = await self._set_status(QuizSession.Status.REVEAL)
        communicator, _ = await self.connect(code=session.code)
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(communicator, "ticket")
        choice_id = await self.first_choice_id(True)
        await communicator.send_json_to(
            {"action": "answer", "choice_id": choice_id}
        )
        rejected = await self.recv_event(communicator, "answer_rejected")
        self.assertIn("locked", rejected["error"].lower())
        await communicator.disconnect()

    async def test_reconnect_with_ticket_restores_participant(self):
        await self.start_question()
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        ticket = (await self.recv_event(communicator, "ticket"))["ticket"]
        await self.recv_event(communicator, "state")
        await communicator.disconnect()

        participant = await self.get_participant("Amina")
        self.assertEqual(participant.api_token, hash_ticket(ticket))

        again, connected = await self.connect(ticket=ticket)
        self.assertTrue(connected)
        state = None
        for _ in range(12):
            payload = await again.receive_json_from(timeout=5)
            if payload.get("event") == "state":
                state = payload["state"]
        self.assertIsNotNone(state["participant"])
        self.assertEqual(state["participant"]["name"], "Amina")
        await again.disconnect()

    async def test_answer_over_websocket_scores_in_database(self):
        await self.start_question()
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(communicator, "ticket")
        choice_id = await self.first_choice_id(True)
        await communicator.send_json_to(
            {"action": "answer", "choice_id": choice_id}
        )
        answered = await self.recv_event(communicator, "answered")
        participant = await self.get_participant("Amina")
        self.assertEqual(participant.score, answered["result"]["points"])
        await communicator.disconnect()

    async def test_ping_pong(self):
        communicator, _ = await self.connect()
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "ping"})
        payload = await self.recv_event(communicator, "pong")
        self.assertIsNotNone(payload)
        await communicator.disconnect()

    async def test_jwt_over_websocket_links_participant_to_account(self):
        await self.start_question()
        from rest_framework_simplejwt.tokens import RefreshToken

        token = str(RefreshToken.for_user(self.student).access_token)
        communicator = WebsocketCommunicator(
            application=self.application(),
            path=f"/ws/quiz/{self.session.code}/?token={token}",
        )
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(communicator, "ticket")
        await self.recv_event(communicator, "state")

        participant = await self._participant_named("Amina")
        self.assertEqual(participant.user_id, self.student.id)
        await communicator.disconnect()

    async def test_reconnect_with_jwt_only_restores_participant(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = str(RefreshToken.for_user(self.student).access_token)
        first = WebsocketCommunicator(
            application=self.application(),
            path=f"/ws/quiz/{self.session.code}/?token={token}",
        )
        await first.connect(timeout=5)
        await self.recv_event(first, "state")
        await first.send_json_to({"action": "join", "nickname": "Amina"})
        await self.recv_event(first, "ticket")
        await self.recv_event(first, "state")
        await first.disconnect()

        second = WebsocketCommunicator(
            application=self.application(),
            path=f"/ws/quiz/{self.session.code}/?token={token}",
        )
        connected, _ = await second.connect(timeout=5)
        self.assertTrue(connected)
        state = None
        for _ in range(12):
            payload = await second.receive_json_from(timeout=5)
            if payload.get("event") == "state":
                state = payload["state"]
        self.assertIsNotNone(state["participant"])
        self.assertEqual(state["participant"]["name"], "Amina")
        await second.disconnect()

    async def test_invalid_jwt_falls_back_to_guest(self):
        communicator = WebsocketCommunicator(
            application=self.application(),
            path=f"/ws/quiz/{self.session.code}/?token=not-a-real-token",
        )
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Guest"})
        await self.recv_event(communicator, "ticket")
        await self.recv_event(communicator, "state")
        participant = await self._participant_named("Guest")
        self.assertIsNone(participant.user_id)
        await communicator.disconnect()

    async def test_same_account_rejoining_is_allowed(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = str(RefreshToken.for_user(self.student).access_token)
        await Participant.objects.acreate(
            session=self.session, name="Amina", user=self.student
        )
        communicator = WebsocketCommunicator(
            application=self.application(),
            path=f"/ws/quiz/{self.session.code}/?token={token}",
        )
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)
        await self.recv_event(communicator, "state")
        await communicator.send_json_to({"action": "join", "nickname": "Amina"})
        ticket = await self.recv_event(communicator, "ticket")
        self.assertTrue(ticket["ticket"])
        self.assertEqual(await self.participant_count(), 1)
        await communicator.disconnect()

    @database_sync_to_async
    def _participant_named(self, name):
        return Participant.objects.get(session=self.session, name=name)

    @database_sync_to_async
    def _set_teams(self, enabled):
        session = QuizSession.objects.get(pk=self.session.pk)
        session.teams_enabled = enabled
        session.save()
        return session

    @database_sync_to_async
    def _set_status(self, status):
        session = QuizSession.objects.get(pk=self.session.pk)
        session.status = status
        session.save()
        return session
