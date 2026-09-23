from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import ActivityLog, Answer, Module, Participant, Question, QuizSession

User = get_user_model()


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_staff:
            messages.error(request, "You don't have access to the admin panel.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return wrapped


def _paginate(request, queryset, per=25):
    page = request.GET.get("page")
    return Paginator(queryset, per).get_page(page)


def _base_query(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


class AdminUserForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "admin-input"}))
    email = forms.EmailField(
        required=False, widget=forms.EmailInput(attrs={"class": "admin-input"})
    )
    first_name = forms.CharField(
        max_length=150, required=False, widget=forms.TextInput(attrs={"class": "admin-input"})
    )
    last_name = forms.CharField(
        max_length=150, required=False, widget=forms.TextInput(attrs={"class": "admin-input"})
    )
    role = forms.ChoiceField(
        choices=[("teacher", "Teacher"), ("student", "Student")],
        initial="student",
        widget=forms.Select(attrs={"class": "admin-input"}),
    )
    is_active = forms.BooleanField(
        required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "admin-checkbox"})
    )
    is_staff = forms.BooleanField(
        required=False, label="Admin access", widget=forms.CheckboxInput(attrs={"class": "admin-checkbox"})
    )
    password = forms.CharField(
        required=False,
        label="Password",
        help_text="Leave blank to keep the current password.",
        widget=forms.PasswordInput(attrs={"class": "admin-input", "autocomplete": "new-password"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        instance = getattr(self, "instance", None)
        if (
            User.objects.filter(username__iexact=username)
            .exclude(pk=instance.pk if instance else None)
            .exists()
        ):
            raise forms.ValidationError("A user with this username already exists.")
        return username


@admin_required
def index(request):
    sessions = QuizSession.objects
    context = {
        "stats": {
            "users": User.objects.count(),
            "teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "students": User.objects.filter(role=User.Role.STUDENT).count(),
            "modules": Module.objects.count(),
            "questions": Question.objects.count(),
            "sessions": sessions.count(),
            "live_sessions": sessions.filter(
                status__in=["waiting", "question", "reveal"]
            ).count(),
            "participants": Participant.objects.count(),
            "answers": Answer.objects.count(),
        },
        "recent_sessions": sessions.select_related("module", "host")
        .annotate(num_players=Count("participants"))[:6],
    }
    return render(request, "admin/index.html", context)


@admin_required
def users(request):
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    queryset = User.objects.all().order_by("-date_joined")
    if q:
        queryset = queryset.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    if role in ("teacher", "student"):
        queryset = queryset.filter(role=role)
    return render(
        request,
        "admin/users.html",
        {"users": _paginate(request, queryset), "q": q, "role": role, "base_query": _base_query(request)},
    )


@admin_required
def user_create(request):
    if request.method == "POST":
        form = AdminUserForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            if not data["password"]:
                form.add_error("password", "Set a password for the new user.")
            else:
                user = User.objects.create_user(
                    username=data["username"],
                    email=data["email"] or "",
                    password=data["password"],
                )
                user.first_name = data["first_name"]
                user.last_name = data["last_name"]
                user.role = data["role"]
                user.is_active = data["is_active"]
                user.is_staff = data["is_staff"]
                user.save()
                messages.success(request, f"User '{user.username}' created.")
                log_activity(request.user, ActivityLog.Action.USER_CREATED, user.username)
                return redirect("admin:users")
    else:
        form = AdminUserForm()
    return render(request, "admin/user_form.html", {"form": form, "mode": "create"})


@admin_required
def user_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        form = AdminUserForm(request.POST)
        form.instance = user
        if form.is_valid():
            data = form.cleaned_data
            if data["password"]:
                user.set_password(data["password"])
            user.username = data["username"]
            user.email = data["email"] or ""
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.role = data["role"]
            user.is_active = data["is_active"]
            user.is_staff = data["is_staff"]
            user.save()
            messages.success(request, f"User '{user.username}' updated.")
            log_activity(request.user, ActivityLog.Action.USER_UPDATED, user.username)
            return redirect("admin:users")
    else:
        form = AdminUserForm(
            initial={
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
            }
        )
        form.instance = user
    return render(request, "admin/user_form.html", {"form": form, "mode": "edit", "edit_user": user})


@admin_required
def user_delete(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
        else:
            name = user.username
            user.delete()
            messages.success(request, f"User '{name}' deleted.")
            log_activity(request.user, ActivityLog.Action.USER_DELETED, name)
    return redirect("admin:users")


@admin_required
def modules(request):
    q = request.GET.get("q", "").strip()
    queryset = (
        Module.objects.select_related("teacher")
        .annotate(num_questions=Count("questions"))
        .order_by("-created_at")
    )
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(teacher__username__icontains=q))
    return render(
        request,
        "admin/modules.html",
        {"modules": _paginate(request, queryset), "q": q, "base_query": _base_query(request)},
    )


@admin_required
def module_detail(request, module_id):
    module = get_object_or_404(Module.objects.select_related("teacher"), pk=module_id)
    questions = module.questions.prefetch_related("choices")
    return render(
        request,
        "admin/module_detail.html",
        {"module": module, "questions": questions},
    )


@admin_required
def module_delete(request, module_id):
    module = get_object_or_404(Module, pk=module_id)
    if request.method == "POST":
        title = module.title
        module.delete()
        messages.success(request, f"Module '{title}' deleted.")
        log_activity(request.user, ActivityLog.Action.MODULE_DELETED, title)
    return redirect("admin:modules")


@admin_required
def sessions(request):
    status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()
    queryset = (
        QuizSession.objects.select_related("module", "host")
        .annotate(num_players=Count("participants"))
        .order_by("-created_at")
    )
    if status == "live":
        queryset = queryset.filter(status__in=["waiting", "question", "reveal"])
    elif status == "ended":
        queryset = queryset.filter(status="ended")
    if q:
        queryset = queryset.filter(
            Q(code__icontains=q) | Q(module__title__icontains=q) | Q(host__username__icontains=q)
        )
    return render(
        request,
        "admin/sessions.html",
        {"sessions": _paginate(request, queryset), "q": q, "status": status, "base_query": _base_query(request)},
    )


@admin_required
def session_detail(request, session_id):
    session = get_object_or_404(
        QuizSession.objects.select_related("module", "host"), pk=session_id
    )
    participants_qs = session.participants.order_by("-score", "joined_at")
    answers_qs = (
        Answer.objects.filter(participant__session=session)
        .select_related("participant", "question", "choice")
        .order_by("-answered_at")
    )
    stats = {
        "players": participants_qs.count(),
        "answered": answers_qs.count(),
        "correct": answers_qs.filter(choice__is_correct=True).count(),
    }
    participants = Paginator(participants_qs, 15).get_page(
        request.GET.get("page", "1")
    )
    answers = Paginator(answers_qs, 15).get_page(
        request.GET.get("apage", "1")
    )
    return render(
        request,
        "admin/session_detail.html",
        {
            "session": session,
            "participants": participants,
            "answers": answers,
            "stats": stats,
        },
    )


@admin_required
def session_end(request, session_id):
    session = get_object_or_404(QuizSession, pk=session_id)
    if request.method == "POST" and session.status != QuizSession.Status.ENDED:
        session.status = QuizSession.Status.ENDED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])
        messages.success(request, f"Session {session.code} ended.")
        log_activity(
            request.user,
            ActivityLog.Action.SESSION_ENDED,
            f"{session.code} · {session.module.title}",
        )
    return redirect("admin:session_detail", session_id=session.id)


@admin_required
def participants(request):
    q = request.GET.get("q", "").strip()
    queryset = Participant.objects.select_related("session__module").order_by("-score")
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(session__code__icontains=q)
            | Q(session__module__title__icontains=q)
        )
    return render(
        request,
        "admin/participants.html",
        {"participants": _paginate(request, queryset), "q": q, "base_query": _base_query(request)},
    )


@admin_required
def answers(request):
    q = request.GET.get("q", "").strip()
    correct = request.GET.get("correct", "").strip()
    queryset = (
        Answer.objects.select_related("participant", "question", "choice", "participant__session__module")
        .order_by("-answered_at")
    )
    if q:
        queryset = queryset.filter(
            Q(participant__name__icontains=q)
            | Q(question__text__icontains=q)
            | Q(choice__text__icontains=q)
        )
    if correct == "yes":
        queryset = queryset.filter(choice__is_correct=True)
    elif correct == "no":
        queryset = queryset.filter(choice__is_correct=False)
    return render(
        request,
        "admin/answers.html",
        {"answers": _paginate(request, queryset), "q": q, "correct": correct, "base_query": _base_query(request)},
    )


@admin_required
def teachers(request):
    q = request.GET.get("q", "").strip()
    queryset = (
        User.objects.filter(role=User.Role.TEACHER)
        .annotate(
            module_count=Count("modules", distinct=True),
            session_count=Count("hosted_sessions", distinct=True),
            ended_count=Count(
                "hosted_sessions",
                distinct=True,
                filter=Q(hosted_sessions__status=QuizSession.Status.ENDED),
            ),
            player_count=Count(
                "hosted_sessions__participants",
                distinct=True,
            ),
            answer_count=Count("hosted_sessions__participants__answers", distinct=True),
            activity_count=Count("activity_logs", distinct=True),
        )
        .order_by("-date_joined")
    )
    if q:
        queryset = queryset.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    return render(
        request,
        "admin/teachers.html",
        {"teachers": _paginate(request, queryset), "q": q, "base_query": _base_query(request)},
    )


@admin_required
def logs(request):
    q = request.GET.get("q", "").strip()
    action = request.GET.get("action", "").strip()
    actor_id = request.GET.get("actor", "").strip()
    queryset = ActivityLog.objects.select_related("actor").order_by("-created_at")
    if q:
        queryset = queryset.filter(
            Q(actor__username__icontains=q)
            | Q(actor__first_name__icontains=q)
            | Q(target__icontains=q)
        )
    if action and action in ActivityLog.Action.values:
        queryset = queryset.filter(action=action)
    if actor_id.isdigit():
        queryset = queryset.filter(actor_id=int(actor_id))
    actor_user = None
    if actor_id.isdigit():
        actor_user = User.objects.filter(pk=int(actor_id)).first()
    return render(
        request,
        "admin/logs.html",
        {
            "logs": _paginate(request, queryset, per=30),
            "q": q,
            "action": action,
            "action_options": ActivityLog.Action.choices,
            "actor_user": actor_user,
            "actor_id": actor_id,
            "base_query": _base_query(request),
        },
    )