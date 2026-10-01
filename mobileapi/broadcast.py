import asyncio

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def group_for(code):
    # Normalise case: the consumer upper-codes the URL segment while views pass
    # session.code, so normalising here keeps both sides on one group name.
    return f"quiz.{(code or '').upper()}"


def broadcast(code, payload):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            group_for(code), {"type": "quiz.event", "payload": payload}
        )
    except Exception:
        pass


def broadcast_state(code, participant_id=None, include_leaderboard=True):
    from mobileapi.quizstate import session_state
    from quiz.models import Participant, QuizSession

    session = QuizSession.objects.filter(code=code).first()
    if session is None:
        return
    participant = None
    if participant_id:
        participant = Participant.objects.filter(
            id=participant_id, session=session
        ).first()
    broadcast(
        code,
        {
            "event": "state",
            "state": session_state(
                session, participant, include_leaderboard=include_leaderboard
            ),
        },
    )


def broadcast_to_all(code, event, **extra):
    broadcast(code, {"event": event, **extra})


async def start_ticker(code, interval=1.0):
    from channels.db import database_sync_to_async

    from mobileapi.quizstate import advance_expired
    from quiz.models import QuizSession

    channel_layer = get_channel_layer()
    group = group_for(code)

    @database_sync_to_async
    def load():
        session = QuizSession.objects.filter(code=code).first()
        if session is None:
            return None
        session, changed = advance_expired(session)
        tick = {
            "status": session.status,
            "paused": session.is_paused,
            "current_index": session.current_index,
            "total_questions": session.question_count,
            "seconds_remaining": session.seconds_remaining(),
        }
        return tick, changed

    while True:
        try:
            await asyncio.sleep(interval)
            result = await load()
            if result is None:
                return
            tick, changed = result
            if changed:
                await channel_layer.group_send(
                    group,
                    {"type": "quiz.event", "payload": {"event": "reveal"}},
                )
                return
            await channel_layer.group_send(
                group, {"type": "quiz.event", "payload": {"event": "tick", "tick": tick}}
            )
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(interval)
