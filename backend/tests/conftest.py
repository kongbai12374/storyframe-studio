import os

os.environ.setdefault("SECRET_KEY", "synthetic-test-secret")
os.environ.setdefault("ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
import pytest, time, json, io
from django.contrib.auth.models import User
from django.test import Client
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture
def context(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_ROOT.mkdir()
    settings.DATA_DIR = tmp_path
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"timestamp": time.time(), "available_mb": 900}))
    settings.HOST_METRICS = str(metrics)
    a = User.objects.create_user("alice", password="a-strong-test-password")
    b = User.objects.create_user("bob", password="a-strong-test-password")
    c = Client()
    c.force_login(a)
    return a, b, c


@pytest.fixture
def picture():
    buf = io.BytesIO()
    Image.new("RGB", (640, 360), (110, 145, 125)).save(buf, "PNG")
    return SimpleUploadedFile("frame.png", buf.getvalue(), content_type="image/png")
