import json

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    JoinForm,
    JoinNameForm,
    LoginForm,
    ModuleForm,
    ProfileForm,
    ProfilePasswordForm,
    QuestionForm,
    SignUpForm,
)
from .models import (
    ActivityLog,
    Answer,
    BankChoice,
    BankQuestion,
    Module,
    Participant,
    Question,
    QuizSession,
    User,
    log_activity,
)
from . import charts, reporting


def _leaderboard_list(session):
    return sorted(session.participants.all(), key=lambda p: p.score, reverse=True)


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
            log_activity(user, ActivityLog.Action.SIGNUP, user.username)
            messages.success(request, f"Welcome to ShamsQuiz, {user.username}!")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("admin:index" if request.user.is_staff else "dashboard")
    if request.method == "POST":
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            log_activity(user, ActivityLog.Action.LOGIN, user.username)
            return redirect("admin:index" if user.is_staff else "dashboard")
    else:
        form = LoginForm()
    return render(request, "registration/login.html", {"form": form})


def logout_view(request):
    if request.user.is_authenticated:
        log_activity(request.user, ActivityLog.Action.LOGOUT, request.user.username)
        logout(request)
    return redirect("home")


@login_required
def dashboard(request):
    user = request.user
    if user.is_teacher:
        modules_count = Module.objects.filter(teacher=user).count()
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
        live_sessions_list = (
            QuizSession.objects.filter(
                host=user,
            )
            .exclude(status=QuizSession.Status.ENDED)
            .select_related("module")
            .annotate(players=Count("participants"))
            .order_by("-created_at")
        )
        recent = (
            QuizSession.objects.filter(
                host=user,
                status=QuizSession.Status.ENDED,
            )
            .select_related("module")
            .annotate(num_players=Count("participants"))
            .order_by("-ended_at", "-created_at")
        )
        paginator = Paginator(recent, 4)
        try:
            recent_page = paginator.page(request.GET.get("page", "1"))
        except (EmptyPage, PageNotAnInteger):
            recent_page = paginator.page(1)
        context = {
            "modules_count": modules_count,
            "total_questions": total_questions,
            "live_sessions": live_sessions,
            "live_sessions_list": live_sessions_list,
            "recent_page": recent_page,
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
    response = _teacher_only(request)
    if response:
        return response
    modules = (
        Module.objects.filter(teacher=request.user)
        .annotate(num_questions=Count("questions"))
        .order_by("-updated_at")
    )
    paginator = Paginator(modules, 12)
    try:
        page = paginator.page(request.GET.get("page", "1"))
    except (EmptyPage, PageNotAnInteger):
        page = paginator.page(1)
    return render(request, "quiz/module_list.html", {"page": page})


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
            log_activity(
                request.user,
                ActivityLog.Action.MODULE_CREATED,
                module.title,
            )
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
    log_activity(request.user, ActivityLog.Action.MODULE_DELETED, module.title)
    module.delete()
    messages.success(request, "Module deleted.")
    return redirect("module_list")


@login_required
def module_detail(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    questions = module.questions.order_by("-is_active", "order", "id")
    return render(
        request,
        "quiz/module_detail.html",
        {
            "module": module,
            "questions": questions,
            "active_count": module.questions.filter(is_active=True).count(),
            "total_count": module.questions.count(),
            "inactive_count": module.questions.filter(is_active=False).count(),
        },
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


@login_required
@require_POST
def question_toggle(request, module_id, question_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    question = get_object_or_404(Question, pk=question_id, module=module)
    question.is_active = not question.is_active
    question.save(update_fields=["is_active"])
    if question.is_active:
        messages.success(request, "Question reactivated and can be hosted again.")
    else:
        messages.info(request, "Question deactivated. It won't appear in quizzes unless reactivated.")
    return redirect("module_detail", module_id=module.id)


# ---------------- Question bank ----------------


def _teacher_only(request):
    if not request.user.is_teacher:
        messages.error(request, "Teachers only.")
        return redirect("dashboard")
    return None


@login_required
def bank(request):
    response = _teacher_only(request)
    if response:
        return response

    q = request.GET.get("q", "").strip()
    subject = request.GET.get("subject", "").strip()
    show_archived = request.GET.get("archived", "") == "1"
    base = BankQuestion.objects.select_related("added_by").prefetch_related(
        "choices"
    )
    if not show_archived:
        base = base.filter(is_active=True)
    if q:
        base = base.filter(Q(text__icontains=q) | Q(subject__icontains=q))
    if subject:
        base = base.filter(subject=subject)
    questions = base.order_by("-is_active", "subject", "-created_at")

    subject_counts = (
        base.values("subject")
        .exclude(subject="")
        .annotate(count=Count("id"))
        .order_by("subject")
    )
    archived_count = BankQuestion.objects.filter(is_active=False).count()
    modules = Module.objects.filter(teacher=request.user)

    params = request.GET.copy()
    params.pop("page", None)
    base_query = params.urlencode()

    paginator = Paginator(questions, 10)
    page = paginator.get_page(request.GET.get("page", "1"))

    return render(
        request,
        "quiz/bank.html",
        {
            "page": page,
            "subject_counts": subject_counts,
            "subject": subject,
            "q": q,
            "modules": modules,
            "show_archived": show_archived,
            "archived_count": archived_count,
            "base_query": base_query,
        },
    )


@login_required
@require_POST
def bank_question_toggle(request, bank_id):
    response = _teacher_only(request)
    if response:
        return response
    bank_q = get_object_or_404(BankQuestion, pk=bank_id)
    bank_q.is_active = not bank_q.is_active
    bank_q.save(update_fields=["is_active"])
    if bank_q.is_active:
        messages.success(request, "Bank question reactivated.")
    else:
        messages.info(request, "Bank question deactivated — it won't appear in the bank list.")
    return redirect("bank")


@login_required
def bank_question_delete(request, bank_id):
    response = _teacher_only(request)
    if response:
        return response
    bank_q = get_object_or_404(BankQuestion, pk=bank_id)
    bank_q.delete()
    messages.success(request, "Bank question deleted.")
    return redirect("bank")


@login_required
def bank_add(request, bank_id):
    response = _teacher_only(request)
    if response:
        return response
    bank_q = get_object_or_404(BankQuestion, pk=bank_id)
    try:
        module = Module.objects.get(pk=int(request.POST.get("module_id", "")), teacher=request.user)
    except (ValueError, Module.DoesNotExist):
        messages.error(request, "Choose one of your modules to import into.")
        return redirect("bank")
    question = Question.objects.create(
        module=module,
        text=bank_q.text,
        time_limit=bank_q.time_limit,
        points=bank_q.points,
    )
    for choice in bank_q.choices.all():
        question.choices.create(
            text=choice.text,
            is_correct=choice.is_correct,
            order=choice.order,
        )
    log_activity(
        request.user,
        ActivityLog.Action.BANK_ADDED,
        f"{bank_q.text[:60]} → {module.title}",
    )
    messages.success(request, f"Question imported into “{module.title}”.")
    return redirect("bank")


@login_required
def question_to_bank(request, module_id, question_id):
    response = _teacher_only(request)
    if response:
        return response
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    question = get_object_or_404(Question, pk=question_id, module=module)
    bank_q = BankQuestion.objects.create(
        text=question.text,
        subject=module.title,
        time_limit=question.time_limit,
        points=question.points,
        added_by=request.user,
    )
    for choice in question.choices.all():
        BankChoice.objects.create(
            question=bank_q,
            text=choice.text,
            is_correct=choice.is_correct,
            order=choice.order,
        )
    log_activity(
        request.user,
        ActivityLog.Action.QUESTION_BANKED,
        f"{question.text[:60]} ← {module.title}",
    )
    messages.success(request, "Question saved to the bank.")
    return redirect("module_detail", module_id=module.id)


# ---------------- Live quiz: host ----------------


@login_required
def teacher_profile(request):
    profile_form = ProfileForm(request.POST or None, instance=request.user)
    password_form = ProfilePasswordForm(request.POST or None, user=request.user)
    if request.method == "POST":
        if "update_profile" in request.POST and profile_form.is_valid():
            profile_form.save()
            log_activity(
                request.user,
                ActivityLog.Action.PROFILE_UPDATED,
                request.user.username,
            )
            messages.success(request, "Profile details saved.")
            return redirect("profile")
        if "change_password" in request.POST and password_form.is_valid():
            request.user.set_password(password_form.cleaned_data["new_password1"])
            request.user.save()
            update_session_auth_hash(request, request.user)
            log_activity(
                request.user,
                ActivityLog.Action.PASSWORD_CHANGED,
                request.user.username,
            )
            messages.success(request, "Password changed.")
            return redirect("profile")
    return render(
        request,
        "quiz/teacher_profile.html",
        {"profile_form": profile_form, "password_form": password_form},
    )


@login_required
def start_quiz(request, module_id):
    module = get_object_or_404(Module, pk=module_id, teacher=request.user)
    if module.questions.filter(is_active=True).count() < 1:
        messages.error(
            request,
            "Add at least one active question before hosting.",
        )
        return redirect("module_detail", module_id=module.id)
    session = QuizSession.objects.create(
        module=module,
        host=request.user,
    )
    log_activity(
        request.user,
        ActivityLog.Action.QUIZ_HOSTED,
        f"{module.title} ({session.code})",
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
        log_activity(
            request.user,
            ActivityLog.Action.QUIZ_ENDED,
            f"{session.code} · {session.module.title}",
        )
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


def scoreboard(request, code):
    session = get_object_or_404(QuizSession, code=code)
    leaderboard = sorted(
        session.participants.all(), key=lambda p: p.score, reverse=True
    )
    top = leaderboard[0].score if leaderboard else 0
    rows = []
    for p in leaderboard:
        correct = p.answers.filter(choice__is_correct=True).count()
        attempted = p.answers.count()
        rows.append(
            {
                "participant": p,
                "score": p.score,
                "correct": correct,
                "attempted": attempted,
                "accuracy": round(correct / attempted * 100) if attempted else 0,
                "pct": round(p.score / top * 100) if top else 0,
            }
        )
    return render(
        request,
        "quiz/scoreboard.html",
        {
            "session": session,
            "rows": rows,
            "top": top,
            "avg_score": round(sum(r["score"] for r in rows) / len(rows))
            if rows
            else 0,
            "best_accuracy": max((r["accuracy"] for r in rows), default=0),
            "my_id": request.session.get("participant_id"),
        },
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
                log_activity(
                    session.host,
                    ActivityLog.Action.QUIZ_JOINED,
                    f"{name} joined {session.code}",
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


# ---------------- Teacher: history, analytics, reports ----------------


@login_required
def teacher_history(request):
    user = request.user
    if not user.is_teacher:
        messages.error(request, "Teachers only.")
        return redirect("dashboard")

    all_sessions = list(
        QuizSession.objects.filter(
            host=user,
            status=QuizSession.Status.ENDED,
        )
        .select_related("module")
        .annotate(
            num_players=Count("participants"),
            avg_score=Avg("participants__score"),
        )
        .order_by("-ended_at", "-created_at")
    )

    paginator = Paginator(all_sessions, 5)
    page = paginator.get_page(request.GET.get("page", "1"))
    for s in page.object_list:
        s.sorted_players = sorted(
            s.participants.all(), key=lambda p: p.score, reverse=True
        )[:5]

    labels = [
        f"{s.ended_at:%b %d}" if s.ended_at else f"{s.created_at:%b %d}"
        for s in all_sessions
    ]
    scores = [round(s.avg_score or 0) for s in all_sessions]
    player_counts = [s.num_players for s in all_sessions]

    correct = Answer.objects.filter(
        participant__session__host=user,
        choice__is_correct=True,
    ).count()
    wrong = Answer.objects.filter(
        participant__session__host=user,
        choice__is_correct=False,
    ).count()

    totals = {
        "quizzes": len(all_sessions),
        "players": sum(player_counts),
        "answers": correct + wrong,
        "accuracy": round(correct / (correct + wrong) * 100)
        if (correct + wrong)
        else 0,
    }

    return render(
        request,
        "quiz/teacher_history.html",
        {
            "sessions": all_sessions,
            "page": page,
            "trend_chart": charts.score_trend(labels, scores),
            "participation_chart": charts.participation_chart(labels, player_counts),
            "accuracy_donut": charts.accuracy_donut(correct, wrong),
            "totals": totals,
        },
    )


@login_required
def session_chart(request, session_id):
    session = get_object_or_404(QuizSession, pk=session_id, host=request.user)
    participants = list(session.participants.all())
    png = charts.leaderboard_png(
        [p.name for p in participants],
        [p.score for p in participants],
    )
    if not png:
        return HttpResponse(status=204)
    return HttpResponse(png, content_type="image/png")


@login_required
def session_report(request, session_id):
    session = get_object_or_404(QuizSession, pk=session_id, host=request.user)
    leaderboard = _leaderboard_list(session)
    pdf = reporting.build_session_report(session, leaderboard)
    log_activity(
        request.user,
        ActivityLog.Action.REPORT_DOWNLOADED,
        f"{session.code} · {session.module.title}",
    )
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="shamsquiz_report_{session.code}.pdf"'
    )
    return response