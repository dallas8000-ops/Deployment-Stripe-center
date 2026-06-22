from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.middleware import RequestIdMiddleware


@override_settings(
    MIDDLEWARE=[
        "apps.core.middleware.RequestIdMiddleware",
        "django.middleware.common.CommonMiddleware",
    ],
    ROOT_URLCONF="config.urls",
)
class RequestIdMiddlewareTests(SimpleTestCase):
    def test_adds_request_id_header(self):
        factory = RequestFactory()
        request = factory.get("/health/")

        def get_response(req):
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = RequestIdMiddleware(get_response)
        response = middleware(request)
        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])

    def test_preserves_incoming_request_id(self):
        factory = RequestFactory()
        request = factory.get("/health/", HTTP_X_REQUEST_ID="client-fixed-id")

        def get_response(req):
            from django.http import HttpResponse

            self.assertEqual(req.request_id, "client-fixed-id")
            return HttpResponse("ok")

        middleware = RequestIdMiddleware(get_response)
        response = middleware(request)
        self.assertEqual(response["X-Request-ID"], "client-fixed-id")
