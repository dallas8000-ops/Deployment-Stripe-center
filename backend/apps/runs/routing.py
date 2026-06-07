from django.urls import re_path

from .consumers import PipelineRunConsumer

websocket_urlpatterns = [
    re_path(r"ws/runs/(?P<run_id>[0-9a-f-]+)/$", PipelineRunConsumer.as_asgi()),
]
