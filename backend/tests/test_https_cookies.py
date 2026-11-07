from django.test import Client


def test_https_marks_csrf_cookie_secure(context):
    response = Client().get("/api/csrf/", secure=True)
    assert response.status_code == 200
    assert response.cookies["csrftoken"]["secure"]


def test_loopback_http_retains_local_cookie(context):
    response = Client().get("/api/csrf/")
    assert response.status_code == 200
    assert not response.cookies["csrftoken"]["secure"]
