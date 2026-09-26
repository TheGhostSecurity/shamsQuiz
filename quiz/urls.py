from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register_code, name="register"),
    path(
        "register/account/",
        views.register_account,
        name="register_account",
    ),
    path(
        "login/",
        views.login_view,
        name="login",
    ),
    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.teacher_profile, name="profile"),
    path("teacher/history/", views.teacher_history, name="teacher_history"),
    path(
        "teacher/history/<int:session_id>/report/",
        views.session_report,
        name="session_report",
    ),
    path(
        "teacher/history/<int:session_id>/export/",
        views.session_export_csv,
        name="session_export_csv",
    ),
    path(
        "teacher/history/<int:session_id>/chart/",
        views.session_chart,
        name="session_chart",
    ),

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
    path(
        "modules/<int:module_id>/duplicate/",
        views.module_duplicate,
        name="module_duplicate",
    ),
    path(
        "modules/<int:module_id>/export/",
        views.module_export_csv,
        name="module_export_csv",
    ),
    path(
        "modules/<int:module_id>/import/",
        views.module_import_csv,
        name="module_import_csv",
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
    path(
        "modules/<int:module_id>/questions/<int:question_id>/toggle/",
        views.question_toggle,
        name="question_toggle",
    ),
    path(
        "modules/<int:module_id>/questions/<int:question_id>/to-bank/",
        views.question_to_bank,
        name="question_to_bank",
    ),

    # Teacher: question bank
    path("bank/", views.bank, name="bank"),
    path(
        "bank/<int:bank_id>/add-to/",
        views.bank_add,
        name="bank_add",
    ),
    path(
        "bank/<int:bank_id>/toggle/",
        views.bank_question_toggle,
        name="bank_question_toggle",
    ),
    path(
        "bank/<int:bank_id>/delete/",
        views.bank_question_delete,
        name="bank_question_delete",
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
    path("host/<str:code>/pause/", views.host_pause, name="host_pause"),
    path("host/<str:code>/resume/", views.host_resume, name="host_resume"),
    path("host/<str:code>/add-time/", views.host_add_time, name="host_add_time"),
    path("scoreboard/<str:code>/", views.scoreboard, name="scoreboard"),

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