from django.urls import path

from .consumers import QuizConsumer

websocket_urlpatterns = [
    path("ws/quiz/<str:code>/", QuizConsumer.as_asgi()),
]
