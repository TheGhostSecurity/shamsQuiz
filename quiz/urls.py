from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup_view, name="signup"),
    path(
        "login/",
        views.login_view,
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Teacher: modules
    path("modules/", views.module_list, name="module_list"),
    path("modules/new/", views.module_create, name="module_create"),
    path(
        "modules/<int:module_id>/",
        views.module_detail,
        name="module_detail",
    ),
    path(
        "modules/<int:module_id>/edit/",
        views.module_edit,
        name="module_edit",
    ),
    path(
        "modules/<int:module_id>/delete/",
        views.module_delete,
        name="module_delete",
    ),

    # Teacher: questions
    path(
        "modules/<int:module_id>/questions/new/",
        views.question_create,
        name="question_create",
    ),
    path(
        "modules/<int:module_id>/questions/<int:question_id>/edit/",
        views.question_edit,
        name="question_edit",
    ),
    path(
        "modules/<int:module_id>/questions/<int:question_id>/delete/",
        views.question_delete,
        name="question_delete",
    ),

    # Host (teacher)
    path("quiz/<int:module_id>/start/", views.start_quiz, name="start_quiz"),
    path("host/<str:code>/lobby/", views.host_lobby, name="host_lobby"),
    path("host/<str:code>/", views.host_control, name="host_control"),
    path(
        "host/<str:code>/start-question/",
        views.host_start_question,
        name="host_start_question",
    ),
    path(
        "host/<str:code>/reveal/",
        views.host_reveal,
        name="host_reveal",
    ),
    path(
        "host/<str:code>/next-question/",
        views.host_next_question,
        name="host_next_question",
    ),
    path("host/<str:code>/end/", views.host_end_quiz, name="host_end_quiz"),
    path("host/<str:code>/results/", views.host_results, name="host_results"),

    # Student
    path("join/", views.join, name="join"),
    path("join/<str:code>/", views.join_name, name="join_name"),
    path("play/<str:code>/", views.student_play, name="student_play"),

    # API
    path("api/quiz/<str:code>/state/", views.quiz_state, name="quiz_state"),
    path(
        "api/quiz/<str:code>/answer/",
        views.submit_answer,
        name="submit_answer",
    ),
    path(
        "api/quiz/<str:code>/leaderboard/",
        views.leaderboard_json,
        name="leaderboard_json",
    ),
]