from django.urls import path

from . import views_admin

app_name = "admin"

urlpatterns = [
    path("", views_admin.index, name="index"),
    path("users/", views_admin.users, name="users"),
    path("users/new/", views_admin.user_create, name="user_create"),
    path("users/<int:user_id>/edit/", views_admin.user_edit, name="user_edit"),
    path("users/<int:user_id>/delete/", views_admin.user_delete, name="user_delete"),
    path("users/<int:user_id>/deactivate/", views_admin.user_deactivate, name="user_deactivate"),
    path("users/<int:user_id>/reactivate/", views_admin.user_reactivate, name="user_reactivate"),
    path("users/<int:user_id>/archive/", views_admin.user_archive, name="user_archive"),
    path("users/<int:user_id>/restore/", views_admin.user_restore, name="user_restore"),
    path("modules/", views_admin.modules, name="modules"),
    path("modules/<int:module_id>/", views_admin.module_detail, name="module_detail"),
    path("modules/<int:module_id>/delete/", views_admin.module_delete, name="module_delete"),
    path("sessions/", views_admin.sessions, name="sessions"),
    path("sessions/<int:session_id>/", views_admin.session_detail, name="session_detail"),
    path("sessions/<int:session_id>/end/", views_admin.session_end, name="session_end"),
    path("participants/", views_admin.participants, name="participants"),
    path("answers/", views_admin.answers, name="answers"),
    path("teachers/", views_admin.teachers, name="teachers"),
    path("logs/", views_admin.logs, name="logs"),
]