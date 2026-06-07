from django.urls import path

from .views import RecommendView

urlpatterns = [
    path(
        "projects/<slug:project_slug>/ai/recommend/",
        RecommendView.as_view(),
        name="ai-recommend",
    ),
]
