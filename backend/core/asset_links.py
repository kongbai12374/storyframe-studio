"""Private, short-lived capabilities for media explicitly selected for an AI request."""

from django.core import signing
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.permissions import AllowAny
from .models import Asset
from .storage import safe_path

SALT = "storyframe-ai-input-v1"


def asset_link(user, ident):
    asset = Asset.objects.get(pk=ident, user=user)
    token = signing.dumps(
        {"asset": asset.id, "user": user.id}, salt=SALT, compress=True
    )
    filename = (
        "reference.jpg"
        if asset.kind == "image"
        else "reference.wav" if asset.name.lower().endswith(".wav") else "reference.mp3"
    )
    return (
        settings.PUBLIC_ORIGIN.rstrip("/")
        + "/api/asset-links/"
        + token
        + "/"
        + filename
    )


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def asset_link_file(request, token, filename=None):
    try:
        data = signing.loads(token, salt=SALT, max_age=3600)
        asset = Asset.objects.get(pk=data["asset"], user_id=data["user"])
        expected = (
            "reference.jpg"
            if asset.kind == "image"
            else (
                "reference.wav"
                if asset.name.lower().endswith(".wav")
                else "reference.mp3"
            )
        )
        if filename is not None and filename != expected:
            raise Http404()
        path = safe_path(asset.path)
        if not path.is_file():
            raise Http404()
    except (signing.BadSignature, Asset.DoesNotExist, KeyError, TypeError, ValueError):
        raise Http404()
    response = FileResponse(
        path.open("rb"),
        content_type=(
            "image/jpeg"
            if asset.kind == "image"
            else "audio/wav" if asset.name.lower().endswith(".wav") else "audio/mpeg"
        ),
    )
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    return response
