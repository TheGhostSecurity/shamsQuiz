import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    JoinForm,
    JoinNameForm,
    LoginForm,
    ModuleForm,
    QuestionForm,
    SignUpForm,
)
from .models import Answer, Module, Participant, Question, QuizSession, User


def home(request):
    return render(request, "quiz/home.html")


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = form.cleaned_data["role"]
            user.save()
            login(request, user)
            messages.success(request, f"Welcome to ShamsQuiz, {user.username}!")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = LoginForm(data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("dashboard")
    else:
        form = LoginForm()
    return render(request, "registration/login.html", {"form": form})


@login_required
def dashboard(request):
    user = request.user
    if user.is_teacher:
        modules = Module.objects.filter(teacher=user).annotate(
            num_questions=Count("questions")
        )
        total_questions = (
            Question.objects.filter(module__teacher=user).count()
        )
        live_sessions = (
            QuizSession.objects.filter(host=user)
            .exclude(status=QuizSession.Status.ENDED)
            .count()
        )
        total_participants = (
            Participant.objects.filter(
                session__host=user,
                session__status=QuizSession.Status.ENDED,
            ).count()
        )
        context = {
            "modules": modules,
            "total_questions": total_questions,
            "live_sessions": live_sessions,
            "total_participants": total_participants,
        }
        return render(request, "quiz/teacher_dashboard.html", context)

    ended_scores = (
        Participant.objects.filter(
            session__host__isnull=False,
            session__status=QuizSession.Status.ENDED,
        )
        .order_by("-score")[:5]
    )
    return render(
        request,
        "quiz/student_home.html",
        {"top_scores": ended_scores},
    )


# ---------------- Module + Question CRUD ----------------


@login_required
def module_list(request):
    return redirect("dashboard")


@login_required
def module_create(request):
    if not request.user.is_teacher:
        messages.error(request, "Teachers only.")
        return redirect("dashboard")
    if request.method == "POST":
        form = ModuleForm(request.POST)
        if form.is_valid():
            module = form.save(commit=False)
            module.teacher = request.user
            module.save()
            messages.success(request, "Module created. Now add some questions!")
            return redirect("module_detail", module_id=module.id)
    else:
        form = ModuleForm()
    return render(request, "quiz/module_form.html", {"form": form, "mode": "create"})


@login_required
def module_edit(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    if request.method == "POST":
        form = ModuleForm(request.POST, instance=module)
        if form.is_valid():
            form.save()
            messages.success(request, "Module updated.")
            return redirect("module_detail", module_id=module.id)
    else:
        form = ModuleForm(instance=module)
    return render(
        request,
        "quiz/module_form.html",
        {"form": form, "module": module, "mode": "edit"},
    )


@login_required
def module_delete(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    module.delete()
    messages.success(request, "Module deleted.")
    return redirect("module_list")


@login_required
def module_detail(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    questions = module.questions.all()
    return render(
        request,
        "quiz/module_detail.html",
        {"module": module, "questions": questions},
    )


@login_required
def question_create(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.module = module
            question.save()
            form.save_choices(question)
            messages.success(request, "Question added.")
            return redirect("module_detail", module_id=module.id)
    else:
        form = QuestionForm()
    return render(
        request,
        "quiz/question_form.html",
        {"form": form, "module": module, "mode": "create"},
    )


@login_required
def question_edit(request, module_id, question_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    question = get_object_or_404(Question, pk=question_id, module=module)
    if request.method == "POST":
        form = QuestionForm(request.POST, question=question)
        if form.is_valid():
            question = form.save()
            form.save_choices(question)
            messages.success(request, "Question updated.")
            return redirect("module_detail", module_id=module.id)
    else:
        form = QuestionForm(question=question)
    return render(
        request,
        "quiz/question_form.html",
        {"form": form, "module": module, "question": question, "mode": "edit"},
    )


@login_required
def question_delete(request, module_id, question_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    question = get_object_or_404(Question, pk=question_id, module=module)
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect("module_detail", module_id=module.id)


# ---------------- Live quiz: host ----------------


@login_required
def start_quiz(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    if module.questions.count() < 1:
        messages.error(request, "Add at least one question before hosting.")
        return redirect("module_detail", module_id=module.id)
    session = QuizSession.objects.create(
        module=module,
        host=request.user,
    )
    messages.success(request, f"Quiz is live! Code: {session.code}")
    return redirect("host_lobby", code=session.code)


@login_required
def host_lobby(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    if session.status != QuizSession.Status.WAITING:
        return redirect("host_control", code=code)
    return render(request, "quiz/host_lobby.html", {"session": session})


@login_required
def host_control(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    if session.status == QuizSession.Status.WAITING:
        return redirect("host_lobby", code=code)
    return render(request, "quiz/host_control.html", {"session": session})


@login_required
def host_start_question(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    if request.method != "POST":
        return redirect("host_control", code=code)
    question = session.current_question
    if session.status == QuizSession.Status.WAITING:
        session.current_index = 0
    if not question:
        session.status = QuizSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save()
        return redirect("host_control", code=code)
    session.status = QuizSession.Status.QUESTION
    now = timezone.now()
    session.question_started_at = now
    session.question_ends_at = now + timezone.timedelta(
        seconds=question.time_limit
    )
    session.save()
    return redirect("host_control", code=code)


@login_required
def host_reveal(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    if request.method == "POST" and session.status == QuizSession.Status.QUESTION:
        session.status = QuizSession.Status.REVEAL
        session.save(update_fields=["status"])
    return redirect("host_control", code=code)


@login_required
def host_next_question(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    if request.method != "POST":
        return redirect("host_control", code=code)
    session.current_index += 1
    question = session.current_question
    if not question:
        session.status = QuizSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save()
        return redirect("host_control", code=code)
    session.status = QuizSession.Status.QUESTION
    now = timezone.now()
    session.question_started_at = now
    session.question_ends_at = now + timezone.timedelta(
        seconds=question.time_limit
    )
    session.save()
    return redirect("host_control", code=code)


@login_required
def host_end_quiz(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    if request.method == "POST":
        session.status = QuizSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save()
        messages.success(request, "Quiz ended. The podium is live for students.")
    return redirect("host_results", code=code)


@login_required
def host_results(request, code):
    session = get_object_or_404(QuizSession, code=code, host=request.user)
    leaderboard = sorted(
        session.participants.all(), key=lambda p: p.score, reverse=True
    )
    return render(
        request,
        "quiz/host_results.html",
        {"session": session, "leaderboard": leaderboard},
    )


# ---------------- Live quiz: student ----------------


def join(request):
    if request.method == "POST":
        form = JoinForm(request.POST)
        if form.is_valid():
            session = form.session
            request.session["join_code"] = session.code
            if request.user.is_authenticated:
                return redirect("join_name", code=session.code)
            return redirect("join_name", code=session.code)
    else:
        form = JoinForm()
    return render(request, "quiz/join.html", {"form": form})


def join_name(request, code):
    session = get_object_or_404(QuizSession, code=code)
    if session.status == QuizSession.Status.ENDED:
        return render(request, "quiz/session_expired.html", {"session": session})
    if request.method == "POST":
        form = JoinNameForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"].strip()
            if Participant.objects.filter(session=session, name=name).exists():
                messages.error(request, "That name is taken here. Pick another.")
            else:
                participant = Participant.objects.create(
                    session=session, name=name
                )
                request.session["participant_id"] = participant.id
                return redirect("student_play", code=session.code)
    else:
        form = JoinNameForm()
        if request.user.is_authenticated:
            form.initial["name"] = request.user.username
    return render(
        request,
        "quiz/join_name.html",
        {"form": form, "session": session},
    )


def _get_participant(request, session):
    participant = None
    pid = request.session.get("participant_id")
    if pid:
        participant = Participant.objects.filter(id=pid, session=session).first()
    return participant


def student_play(request, code):
    session = get_object_or_404(QuizSession, code=code)
    participant = _get_participant(request, session)
    if participant is None:
        messages.info(request, "Join the quiz first.")
        return redirect("join")
    if session.status == QuizSession.Status.ENDED:
        return render(
            request,
            "quiz/student_results.html",
            {"session": session, "leaderboard": _leaderboard(session)},
        )
    return render(
        request,
        "quiz/student_play.html",
        {
            "session": session,
            "participant": participant,
            "leaderboard": _leaderboard(session),
        },
    )


def _leaderboard(session):
    return sorted(session.participants.all(), key=lambda p: p.score, reverse=True)


def submit_answer(request, code):
    session = get_object_or_404(QuizSession, code=code)
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)
    participant = _get_participant(request, session)
    if participant is None:
        return JsonResponse({"ok": False, "error": "Rejoin quiz"}, status=403)

    if not session.is_accepting_answers():
        return JsonResponse(
            {"ok": False, "error": "Too late — answers are locked."}
        )

    question = session.current_question
    if question is None:
        return JsonResponse({"ok": False, "error": "No active question."})

    try:
        choice_id = int(request.POST.get("choice_id", ""))
        choice = question.choices.get(pk=choice_id)
    except (ValueError, Choice.DoesNotExist, KeyError):
        return JsonResponse({"ok": False, "error": "Invalid choice."})

    if Answer.objects.filter(participant=participant, question=question).exists():
        return JsonResponse({"ok": False, "error": "Already answered."})

    elapsed = max(
        0.0,
        (timezone.now() - session.question_started_at).total_seconds()
        if session.question_started_at
        else session.seconds_remaining(),
    )
    limit = max(1, question.time_limit)
    speed_ratio = max(0.0, min(1.0, (limit - elapsed) / limit))
    points = int(question.points * (0.5 + 0.5 * speed_ratio)) if choice.is_correct else 0

    Answer.objects.create(
        participant=participant,
        question=question,
        choice=choice,
        points_earned=points,
    )
    participant.score += points
    participant.save(
        update_fields=["score"]
    )

    return JsonResponse(
        {
            "ok": True,
            "correct": choice.is_correct,
            "points": points,
        }
    )


# ---------------- Live API (polling) ----------------


def _session_json(session, host_id=None):
    question = session.current_question
    now = timezone.now()

    data = {
        "id": session.id,
        "code": session.code,
        "status": session.status,
        "current_index": session.current_index,
        "total_questions": session.question_count,
        "module_title": session.module.title,
        "question_ends_at": (
            session.question_ends_at.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            if session.question_ends_at
            else None
        ),
        "seconds_remaining": session.seconds_remaining(),
    }

    if question is None:
        data["question"] = None
    elif session.status in (
        QuizSession.Status.QUESTION,
        QuizSession.Status.REVEAL,
    ):
        letters = ["A", "B", "C", "D"]
        choices_data = []
        for i, choice in enumerate(question.choices.all()):
            choices_data.append(
                {
                    "id": choice.id,
                    "text": choice.text,
                    "letter": letters[i % len(letters)],
                    "is_correct": choice.is_correct
                    if session.status == QuizSession.Status.REVEAL
                    else None,
                }
            )
        data["question"] = {
            "index": session.current_index,
            "text": question.text,
            "time_limit": question.time_limit,
            "points": question.points,
            "choices": choices_data,
        }

    if host_id is not None and session.host_id == host_id:
        participants = session.participants.order_by("joined_at")
        data["participants"] = [
            {
                "id": p.id,
                "name": p.name,
                "score": p.score,
                "has_answered": bool(
                    question
                    and Answer.objects.filter(
                        participant=p, question=question
                    ).exists()
                ),
            }
            for p in participants
        ]
        if question:
            data["answered_count"] = Answer.objects.filter(
                participant__session=session, question=question
            ).count()

    return data


def quiz_state(request, code):
    session = get_object_or_404(QuizSession, code=code)

    if session.status == QuizSession.Status.QUESTION:
        now = timezone.now()
        if session.question_ends_at and now >= session.question_ends_at:
            session.status = QuizSession.Status.REVEAL
            session.save(update_fields=["status"])

    if request.user.is_authenticated and session.host_id == request.user.id:
        return JsonResponse(_session_json(session, host_id=request.user.id))

    participant = _get_participant(request, session)
    data = _session_json(session)

    question = session.current_question
    if participant is None:
        data["joined"] = False
    else:
        data["joined"] = True
        data["participant_id"] = participant.id
        data["score"] = participant.score
        if question and Answer.objects.filter(
            participant=participant, question=question
        ).exists():
            answer = Answer.objects.get(participant=participant, question=question)
            data["my_answer"] = {
                "choice_id": answer.choice_id,
                "correct": answer.choice.is_correct,
                "points": answer.points_earned,
            }
        if session.status == QuizSession.Status.ENDED:
            data["leaderboard"] = [
                {"name": p.name, "score": p.score}
                for p in _leaderboard(session)
            ]

    return JsonResponse(data)


def leaderboard_json(request, code):
    session = get_object_or_404(QuizSession, code=code)
    return JsonResponse(
        {
            "leaderboard": [
                {"name": p.name, "score": p.score}
                for p in _leaderboard(session)
            ]
        }
    )