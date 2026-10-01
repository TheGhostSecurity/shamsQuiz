import random

from django.utils import timezone

from quiz.models import Answer, Choice, Participant, QuizSession

LETTERS = ["A", "B", "C", "D"]
POINTS_PER_QUESTION = 1000


def advance_expired(session):
    if session.status != QuizSession.Status.QUESTION:
        return session, False
    if session.question_ends_at and timezone.now() >= session.question_ends_at:
        session.status = QuizSession.Status.REVEAL
        session.save(update_fields=["status"])
        return session, True
    return session, False


def ordered_choices(question, participant=None, shuffle=True):
    ordered = list(question.choices.all())
    if shuffle and participant is not None:
        rng = random.Random(f"{participant.id}:{question.id}")
        rng.shuffle(ordered)
    return ordered


def score_for(session, question, participant, choice):
    elapsed = max(
        0.0,
        (timezone.now() - session.question_started_at).total_seconds()
        if session.question_started_at
        else session.seconds_remaining(),
    )
    limit = max(1, question.time_limit)
    speed_ratio = max(0.0, min(1.0, (limit - elapsed) / limit))
    return int(round(POINTS_PER_QUESTION * speed_ratio)) if choice.is_correct else 0


def ranks_for(session):
    ordered = sorted(
        session.participants.all(), key=lambda p: (-p.score, p.joined_at)
    )
    return {p.id: i + 1 for i, p in enumerate(ordered)}


def leaderboard_rows(session, limit=None):
    ordered = sorted(
        session.participants.all(), key=lambda p: (-p.score, p.joined_at)
    )
    if limit:
        ordered = ordered[:limit]
    rows = []
    for index, p in enumerate(ordered):
        correct = p.answers.filter(choice__is_correct=True).count()
        attempted = p.answers.count()
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "team": p.team,
                "team_label": p.get_team_display(),
                "score": p.score,
                "rank": index + 1,
                "correct": correct,
                "answered": attempted,
                "accuracy": round(correct / attempted * 100) if attempted else 0,
            }
        )
    return rows


def team_totals(session):
    if not session.teams_enabled:
        return []
    totals = {}
    for p in session.participants.all():
        if not p.team:
            continue
        entry = totals.setdefault(
            p.team, {"team": p.team, "label": p.get_team_display(), "score": 0}
        )
        entry["score"] += p.score
    ordered = sorted(totals.values(), key=lambda t: -t["score"])
    for i, t in enumerate(ordered):
        t["rank"] = i + 1
    return ordered


def build_question_payload(session, participant, reveal_correct=False):
    question = session.current_question
    if question is None:
        return None
    ordered = ordered_choices(
        question,
        participant,
        shuffle=(session.status == QuizSession.Status.QUESTION),
    )
    return {
        "id": question.id,
        "index": session.current_index,
        "text": question.text,
        "time_limit": question.time_limit,
        "choices": [
            {
                "id": c.id,
                "text": c.text,
                "letter": LETTERS[i % len(LETTERS)],
                "is_correct": c.is_correct if reveal_correct else None,
            }
            for i, c in enumerate(ordered)
        ],
    }


def my_answer_for(session, participant, question):
    if participant is None or question is None:
        return None
    answer = Answer.objects.filter(
        participant=participant, question=question
    ).first()
    if answer is None:
        return None
    return {
        "choice_id": answer.choice_id,
        "correct": answer.choice.is_correct,
        "points": answer.points_earned,
    }


def session_state(session, participant=None, include_leaderboard=True):
    session, _ = advance_expired(session)
    question = session.current_question
    status = session.status

    payload = {
        "code": session.code,
        "module_title": session.module.title,
        "host_name": session.host.get_full_name() or session.host.username,
        "status": status,
        "paused": session.is_paused,
        "teams_enabled": session.teams_enabled,
        "current_index": session.current_index,
        "total_questions": session.question_count,
        "seconds_remaining": session.seconds_remaining(),
        "question_ends_at": (
            session.question_ends_at.isoformat()
            if session.question_ends_at
            else None
        ),
        "question": None,
        "participant": None,
        "leaderboard": [],
        "teams": [],
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }

    if status in (QuizSession.Status.QUESTION, QuizSession.Status.REVEAL):
        payload["question"] = build_question_payload(
            session,
            participant,
            reveal_correct=(status == QuizSession.Status.REVEAL),
        )

    if participant is not None:
        payload["participant"] = {
            "id": participant.id,
            "name": participant.name,
            "team": participant.team,
            "score": participant.score,
            "has_answered": bool(
                question
                and Answer.objects.filter(
                    participant=participant, question=question
                ).exists()
            ),
        }
        payload["my_answer"] = my_answer_for(session, participant, question)

    if include_leaderboard:
        payload["leaderboard"] = leaderboard_rows(session, limit=5)
        payload["teams"] = team_totals(session)

    if status == QuizSession.Status.ENDED and include_leaderboard:
        payload["leaderboard"] = leaderboard_rows(session)

    return payload


def join_session(session, user, nickname, team=""):
    existing = None
    if user is not None and user.is_authenticated:
        existing = Participant.objects.filter(
            session=session, user=user
        ).first()
    if existing is None:
        existing = Participant.objects.filter(session=session, name=nickname).first()
    if existing is not None:
        existing.user = user if (user and user.is_authenticated) else existing.user
        updates = ["user"]
        if team and existing.team != team:
            existing.team = team
            updates.append("team")
        existing.save(update_fields=updates)
        return existing, False
    participant = Participant.objects.create(
        session=session,
        name=nickname,
        team=team or "",
        user=user if (user and user.is_authenticated) else None,
    )
    return participant, True


def submit(session, participant, choice_id):
    if not session.is_accepting_answers():
        return None, "Too late — answers are locked."

    question = session.current_question
    if question is None:
        return None, "No active question."

    try:
        choice = question.choices.get(pk=int(choice_id))
    except (Choice.DoesNotExist, TypeError, ValueError):
        return None, "Invalid choice."

    if Answer.objects.filter(
        participant=participant, question=question
    ).exists():
        return None, "You already answered this question."

    points = score_for(session, question, participant, choice)
    Answer.objects.create(
        participant=participant,
        question=question,
        choice=choice,
        points_earned=points,
    )
    Participant.objects.filter(pk=participant.pk).update(
        score=participant.score + points
    )
    participant.score += points

    return {
        "ok": True,
        "question_id": question.id,
        "choice_id": choice.id,
        "correct": choice.is_correct,
        "points": points,
        "total_score": participant.score,
    }, None
