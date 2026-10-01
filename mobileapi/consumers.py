import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from quiz.models import Participant, QuizSession, User

from .broadcast import group_for, start_ticker
from .permissions import hash_ticket, new_ticket
from .quizstate import (
    join_session,
    leaderboard_rows,
    session_state,
    submit,
    team_totals,
)

TICKERS = {}
TICKER_LOCKS = {}
TICKER_REFS = {}


class QuizConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.channel_layer = get_channel_layer()
        self.code = (self.scope["url_route"]["kwargs"].get("code") or "").upper()
        self.participant = None
        self.session_id = None
        self.ticket = self._read_ticket()
        self.user = None
        self.issued_ticket = None

        session = await self._load_session()
        if session is None:
            await self.close(code=4404)
            return
        self.session_id = session.id

        self.user = await self._resolve_user()
        await self._restore_participant()
        await self.channel_layer.group_add(group_for(self.code), self.channel_name)
        await self.accept()
        TICKER_REFS[self.code] = TICKER_REFS.get(self.code, 0) + 1
        await self._ensure_ticker()
        await self._send_state()

    async def disconnect(self, code):
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        await channel_layer.group_discard(group_for(self.code), self.channel_name)
        remaining = TICKER_REFS.get(self.code, 1) - 1
        if remaining <= 0:
            TICKER_REFS.pop(self.code, None)
            ticker = TICKERS.pop(self.code, None)
            if ticker is not None:
                ticker.cancel()
            TICKER_LOCKS.pop(self.code, None)
        else:
            TICKER_REFS[self.code] = remaining

    async def receive_json(self, content, **kwargs):
        action = content.get("action")

        if action == "join":
            await self._handle_join(content)
        elif action == "answer":
            await self._handle_answer(content)
        elif action == "state":
            await self._send_state()
        elif action == "ping":
            await self.send_json({"event": "pong"})
        else:
            await self.send_json(
                {"event": "error", "error": f"Unknown action: {action!r}"}
            )

    async def _handle_join(self, content):
        nickname = (content.get("nickname") or "").strip()
        if len(nickname) < 2:
            await self._error("Enter a name with at least 2 characters.")
            return

        session = await self._load_session()
        if session is None:
            await self._error("Quiz not found.")
            return
        if session.status == QuizSession.Status.ENDED:
            await self._error("This quiz has already ended.")
            return

        team = (content.get("team") or "").strip()
        if session.teams_enabled and team not in dict(Participant.Team.choices):
            await self._error("Choose your team before joining.")
            return

        taken = await self._name_taken(session.id, nickname)
        if taken is True:
            await self._error("That name is taken here. Pick another.")
            return
        if taken is not None:
            self.participant, self.issued_ticket = await self._reissue(taken)
            if self.issued_ticket:
                await self.send_json(
                    {"event": "ticket", "ticket": self.issued_ticket}
                )
            await self._send_state()
            return

        self.participant, self.issued_ticket = await self._bind(session, nickname, team)
        if self.issued_ticket:
            await self.send_json({"event": "ticket", "ticket": self.issued_ticket})
        await self._send_state()

    async def _handle_answer(self, content):
        if self.participant is None:
            await self._error("Join the quiz first.")
            return
        result, error = await self._submit_answer(content.get("choice_id"))
        if error:
            await self.send_json({"event": "answer_rejected", "error": error})
            return
        await self.send_json({"event": "answered", "result": result})
        await self._send_leaderboard()

    async def _error(self, message):
        await self.send_json({"event": "error", "error": message})

    async def _send_state(self):
        state = await self._state_payload()
        if state is not None:
            await self.send_json({"event": "state", "state": state})

    async def _send_leaderboard(self):
        session = await self._load_session()
        if session is None:
            return
        rows = await self._leaderboard(session.id)
        teams = await self._teams(session)
        await self.send_json(
            {"event": "leaderboard", "leaderboard": rows, "teams": teams}
        )

    async def _ensure_ticker(self):
        lock = TICKER_LOCKS.setdefault(self.code, asyncio.Lock())
        async with lock:
            ticker = TICKERS.get(self.code)
            if ticker is None or ticker.done():
                ticker = asyncio.create_task(start_ticker(self.code))
                TICKERS[self.code] = ticker

    def _read_ticket(self):
        for key, value in self.scope.get("headers", []):
            if key.lower() == b"x-quiz-ticket":
                return value.decode().strip()
        for part in self.scope.get("query_string", b"").split(b"&"):
            if part.startswith(b"ticket="):
                return part[len(b"ticket="):].decode().strip()
        return ""

    def _read_jwt(self):
        for key, value in self.scope.get("headers", []):
            if key.lower() == b"authorization":
                raw = value.decode().strip()
                if raw.lower().startswith("bearer "):
                    return raw[len("bearer "):].strip()
        for part in self.scope.get("query_string", b"").split(b"&"):
            if part.startswith(b"token="):
                return part[len("token="):].decode().strip()
        return ""

    @database_sync_to_async
    def _resolve_user(self):
        raw = self._read_jwt()
        if not raw:
            return None
        try:
            token = AccessToken(raw)
        except TokenError:
            return None
        user_id = token.get("user_id")
        if not user_id:
            return None
        return User.objects.filter(
            id=user_id, is_active=True, is_archived=False
        ).first()

    async def quiz_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _load_session(self):
        return QuizSession.objects.filter(code=self.code).first()

    @database_sync_to_async
    def _restore_participant(self):
        if self.ticket:
            self.participant = Participant.objects.filter(
                session_id=self.session_id, api_token=hash_ticket(self.ticket)
            ).first()
            if self.participant is not None:
                return
        if self.user is not None:
            self.participant = (
                Participant.objects.filter(
                    session_id=self.session_id, user=self.user
                )
                .order_by("-id")
                .first()
            )
        return self.participant is not None

    @database_sync_to_async
    def _name_taken(self, session_id, nickname):
        existing = Participant.objects.filter(
            session_id=session_id, name=nickname
        ).first()
        if existing is None:
            return None
        if self.user is not None and existing.user_id == self.user.id:
            return existing
        return True

    @database_sync_to_async
    def _reissue(self, participant):
        ticket = new_ticket()
        participant.api_token = hash_ticket(ticket)
        participant.save(update_fields=["api_token"])
        return participant, ticket

    @database_sync_to_async
    def _bind(self, session, nickname, team):
        participant, created = join_session(session, self.user, nickname, team)
        ticket = new_ticket()
        participant.api_token = hash_ticket(ticket)
        participant.save(update_fields=["api_token"])
        return participant, ticket

    @database_sync_to_async
    def _state_payload(self):
        session = QuizSession.objects.filter(id=self.session_id).first()
        if session is None:
            return None
        return session_state(session, self.participant)

    @database_sync_to_async
    def _submit_answer(self, choice_id):
        session = QuizSession.objects.filter(id=self.session_id).first()
        if session is None:
            return None, "Quiz not found."
        participant = Participant.objects.filter(
            id=self.participant.id, session_id=self.session_id
        ).first()
        if participant is None:
            return None, "Join the quiz first."
        self.participant = participant
        return submit(session, participant, choice_id)

    @database_sync_to_async
    def _leaderboard(self, session_id):
        session = QuizSession.objects.filter(id=session_id).first()
        if session is None:
            return []
        return leaderboard_rows(session)

    @database_sync_to_async
    def _teams(self, session):
        return team_totals(session)
