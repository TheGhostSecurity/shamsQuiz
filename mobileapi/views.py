from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from quiz.models import (
    ActivityLog,
    Answer,
    Module,
    Participant,
    QuizSession,
    log_activity,
)

from . import quizstate
from .errors import bad_request
from .permissions import (
    IsActiveNotArchived,
    IsStudent,
    get_ticket_from_request,
    hash_ticket,
    new_ticket,
    participant_for_ticket,
    participant_for_user,
)
from .serializers import (
    JoinSerializer,
    LoginSerializer,
    ModuleSerializer,
    PasswordChangeSerializer,
    StudentRegisterSerializer,
    SubmitAnswerSerializer,
    TeacherUtilSerializer,
    UtilTeacherSerializer,
    UserSerializer,
)

User = get_user_model()


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def ok(**payload):
    payload["ok"] = True
    return Response(payload)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = StudentRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return bad_request(
                "Please fix the highlighted fields.",
                _field_errors(serializer.errors),
            )
        user = serializer.save()
        return ok(tokens=tokens_for(user), user=UserSerializer(user).data)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return bad_request(
                serializer.errors.get("detail", ["Wrong username or password."])[0],
                _field_errors(serializer.errors),
            )
        user = serializer.validated_data["user"]
        log_activity(user, ActivityLog.Action.LOGIN, user.username, "mobile api")
        return ok(tokens=tokens_for(user), user=UserSerializer(user).data)


def _field_errors(errors):
    fields = {}
    for key, value in errors.items():
        if isinstance(value, (list, tuple)):
            fields[key] = [str(v) for v in value]
        else:
            fields[key] = [str(value)]
    return fields


@api_view(["GET", "PATCH"])
@permission_classes([IsActiveNotArchived])
def me(request):
    if request.method == "GET":
        return ok(user=UserSerializer(request.user).data)

    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if not serializer.is_valid():
        return bad_request("Could not save your profile.", _field_errors(serializer.errors))
    user = serializer.save()
    log_activity(user, ActivityLog.Action.PROFILE_UPDATED, user.username, "mobile api")
    return ok(user=UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([IsActiveNotArchived])
def change_password(request):
    serializer = PasswordChangeSerializer(
        data=request.data, context={"request": request}
    )
    if not serializer.is_valid():
        return bad_request("Could not change your password.", _field_errors(serializer.errors))
    serializer.save()
    return ok()


@api_view(["GET"])
@permission_classes([IsActiveNotArchived])
def home(request):
    user = request.user
    upcoming = (
        QuizSession.objects.filter(
            status__in=[
                QuizSession.Status.WAITING,
                QuizSession.Status.QUESTION,
                QuizSession.Status.REVEAL,
            ]
        )
        .select_related("host", "module")
        .order_by("-created_at")[:10]
    )
    payload = {
        "user": UserSerializer(user).data,
        "stats": _user_stats(user),
        "live_quizzes": [
            {
                "code": s.code,
                "module_title": s.module.title,
                "host_name": s.host.get_full_name() or s.host.username,
                "status": s.status,
                "participant_count": s.participants.count(),
            }
            for s in upcoming
        ],
    }
    if not user.is_teacher:
        payload["my_sessions"] = _recent_sessions(user)
    return ok(**payload)


def _user_stats(user):
    participations = Participant.objects.filter(user=user)
    played = participations.count()
    if not played:
        return {
            "quizzes_played": 0,
            "questions_answered": 0,
            "correct_answers": 0,
            "accuracy": 0,
            "best_score": 0,
            "total_score": 0,
        }
    answers = Answer.objects.filter(participant__user=user)
    answered = answers.count()
    correct = answers.filter(choice__is_correct=True).count()
    return {
        "quizzes_played": played,
        "questions_answered": answered,
        "correct_answers": correct,
        "accuracy": round(correct / answered * 100) if answered else 0,
        "best_score": participations.order_by("-score").values_list("score", flat=True).first() or 0,
        "total_score": participations.aggregate(t=Sum("score"))["t"] or 0,
    }


def _recent_sessions(user, limit=10):
    participations = Participant.objects.filter(user=user).select_related(
        "session", "session__module", "session__host"
    )
    rows = []
    for p in participations[:limit]:
        session = p.session
        answered = p.answers.count()
        correct = p.answers.filter(choice__is_correct=True).count()
        rows.append(
            {
                "code": session.code,
                "module_title": session.module.title,
                "host_name": session.host.get_full_name() or session.host.username,
                "played_at": p.joined_at.isoformat(),
                "status": session.status,
                "score": p.score,
                "rank": _rank_in(session, p),
                "total_players": session.participants.count(),
                "answered": answered,
                "correct": correct,
                "accuracy": round(correct / answered * 100) if answered else 0,
            }
        )
    return rows


def _rank_in(session, participant):
    ordered = sorted(
        session.participants.all(), key=lambda p: (-p.score, p.joined_at)
    )
    for i, p in enumerate(ordered):
        if p.id == participant.id:
            return i + 1
    return None


@api_view(["GET"])
@permission_classes([IsStudent])
def modules(request):
    qs = (
        Module.objects.filter(questions__is_active=True)
        .annotate(total=Count("questions", filter=Q(questions__is_active=True)))
        .distinct()
        .order_by("title")
    )
    return ok(
        modules=ModuleSerializer(qs, many=True).data,
        total=qs.count(),
    )


@api_view(["GET"])
@permission_classes([IsActiveNotArchived])
def progress(request):
    if request.user.is_teacher:
        return bad_request(
            "Progress tracking is for student accounts.",
            code=status.HTTP_403_FORBIDDEN,
        )
    return ok(**_progress_payload(request.user))


def _progress_payload(user):
    participations = list(
        Participant.objects.filter(user=user)
        .select_related("session", "session__module", "session__host")
        .order_by("-joined_at")
    )
    ended = [p for p in participations if p.session.status == QuizSession.Status.ENDED]
    answers = Answer.objects.filter(participant__user=user)
    answered = answers.count()
    correct = answers.filter(choice__is_correct=True).count()

    history = []
    modules = {}
    trend = []

    for p in participations:
        session = p.session
        attempted = p.answers.count()
        right = p.answers.filter(choice__is_correct=True).count()
        rank = _rank_in(session, p)
        played_at = session.ended_at or p.joined_at
        history.append(
            {
                "code": session.code,
                "module_title": session.module.title,
                "host_name": session.host.get_full_name() or session.host.username,
                "status": session.status,
                "score": p.score,
                "rank": rank,
                "total_players": session.participants.count(),
                "correct": right,
                "attempted": attempted,
                "accuracy": round(right / attempted * 100) if attempted else 0,
                "played_at": played_at.isoformat(),
            }
        )
        if session.status == QuizSession.Status.ENDED:
            title = session.module.title
            entry = modules.setdefault(
                title, {"title": title, "quizzes": 0, "correct": 0, "attempted": 0}
            )
            entry["quizzes"] += 1
            entry["correct"] += right
            entry["attempted"] += attempted
            trend.append({"label": f"{played_at:%b %d}", "score": p.score})

    module_rows = []
    for entry in modules.values():
        entry["accuracy"] = (
            round(entry["correct"] / entry["attempted"] * 100)
            if entry["attempted"]
            else 0
        )
        module_rows.append(entry)
    module_rows.sort(key=lambda m: (-m["quizzes"], m["title"]))

    ended_scores = [p.score for p in ended]
    return {
        "stats": {
            "quizzes_ended": len(ended),
            "quizzes_joined": len(participations),
            "total_points": sum(ended_scores),
            "correct": correct,
            "answered": answered,
            "accuracy": round(correct / answered * 100) if answered else 0,
            "best_score": max(ended_scores) if ended_scores else 0,
            "average_score": (
                round(sum(ended_scores) / len(ended_scores)) if ended_scores else 0
            ),
        },
        "modules": module_rows,
        "history": history,
        "trend": list(reversed(trend[:10])),
    }


@api_view(["GET"])
@permission_classes([IsStudent])
def utils(request):
    teacher_id = request.query_params.get("teacher", "").strip()
    teachers = (
        User.objects.filter(role=User.Role.TEACHER, utils__is_active=True)
        .distinct()
        .annotate(file_count=Count("utils", filter=Q(utils__is_active=True)))
        .order_by("username")
    )
    selected = None
    if teacher_id.isdigit():
        selected = teachers.filter(pk=int(teacher_id)).first()
    if selected is None:
        selected = teachers.first()

    files = []
    if selected is not None:
        files = TeacherUtilSerializer(
            selected.utils.filter(is_active=True),
            many=True,
            context={"request": request},
        ).data

    return ok(
        teachers=UtilTeacherSerializer(
            teachers, many=True, source="*"
        ).data,
        selected_teacher=(
            {
                "id": selected.id,
                "name": selected.get_full_name() or selected.username,
                "file_count": selected.utils.filter(is_active=True).count(),
            }
            if selected
            else None
        ),
        files=files,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def session_state(request, code):
    session = QuizSession.objects.filter(code=code.strip().upper()).first()
    if session is None:
        return bad_request("No quiz found for that code.", code=status.HTTP_404_NOT_FOUND)

    participant = _resolve_participant(request, session)
    state = quizstate.session_state(session, participant)
    return ok(state=state, joined=participant is not None)


def _resolve_participant(request, session):
    ticket = get_ticket_from_request(request)
    participant = participant_for_ticket(session, ticket)
    if participant is not None:
        return participant
    return participant_for_user(session, request.user)


@api_view(["POST"])
@permission_classes([IsActiveNotArchived])
def join(request):
    serializer = JoinSerializer(data=request.data)
    if not serializer.is_valid():
        return bad_request("Could not join that quiz.", _field_errors(serializer.errors))

    session = serializer.validated_data["session"]
    nickname = serializer.validated_data["nickname"]
    team = serializer.validated_data.get("team", "") or ""

    participant, created = quizstate.join_session(
        session, request.user, nickname, team
    )
    ticket = new_ticket()
    participant.api_token = hash_ticket(ticket)
    participant.save(update_fields=["api_token"])

    if created:
        log_activity(
            session.host,
            ActivityLog.Action.QUIZ_JOINED,
            f"{nickname} joined {session.code}",
        )

    from .broadcast import broadcast_state

    broadcast_state(session.code, participant.id)

    return ok(
        ticket=ticket,
        participant={
            "id": participant.id,
            "name": participant.name,
            "team": participant.team,
            "score": participant.score,
        },
        state=quizstate.session_state(session, participant),
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def submit_answer(request, code):
    session = QuizSession.objects.filter(code=code.strip().upper()).first()
    if session is None:
        return bad_request("No quiz found for that code.", code=status.HTTP_404_NOT_FOUND)

    participant = _resolve_participant(request, session)
    if participant is None:
        return bad_request(
            "Join the quiz first.", code=status.HTTP_403_FORBIDDEN
        )

    serializer = SubmitAnswerSerializer(data=request.data)
    if not serializer.is_valid():
        return bad_request("Invalid answer.", _field_errors(serializer.errors))

    choice_id = serializer.validated_data["choice_id"]
    result, error = quizstate.submit(session, participant, choice_id)
    if error:
        if "already" in error.lower():
            return bad_request(error, code=status.HTTP_409_CONFLICT)
        return bad_request(error)

    from .broadcast import broadcast_state

    broadcast_state(session.code, participant.id)
    return ok(result=result, score=participant.score)


@api_view(["GET"])
@permission_classes([AllowAny])
def scoreboard(request, code):
    session = QuizSession.objects.filter(code=code.strip().upper()).first()
    if session is None:
        return bad_request("No quiz found for that code.", code=status.HTTP_404_NOT_FOUND)
    rows = quizstate.leaderboard_rows(session)
    viewer = None
    participant = _resolve_participant(request, session)
    if participant is not None:
        for row in rows:
            if row["id"] == participant.id:
                viewer = row
                break
    return ok(
        code=session.code,
        module_title=session.module.title,
        status=session.status,
        leaderboard=rows,
        teams=quizstate.team_totals(session),
        me=viewer,
    )
