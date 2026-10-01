from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = "mobileapi"

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/me/", views.me, name="me"),
    path("auth/password/", views.change_password, name="change-password"),
    path("home/", views.home, name="home"),
    path("modules/", views.modules, name="modules"),
    path("progress/", views.progress, name="progress"),
    path("utils/", views.utils, name="utils"),
    path("quiz/join/", views.join, name="join"),
    path("quiz/<str:code>/state/", views.session_state, name="state"),
    path("quiz/<str:code>/answer/", views.submit_answer, name="answer"),
    path("quiz/<str:code>/scoreboard/", views.scoreboard, name="scoreboard"),
]
