from django.urls import include, path

urlpatterns = [
    path("admin/", include("quiz.admin_urls")),
    path("", include("quiz.urls")),
]