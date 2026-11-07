from django.core.files.uploadedfile import SimpleUploadedFile
from .image_api import fetch_image
from .storage import save_upload
from .gateway import GatewayError
from .video import check
from .video_api import node_state


def save_result(job, provider, frozen, value):
    if not isinstance(value, str):
        raise GatewayError("配音结果URL无效")
    blob = fetch_image(job, provider, frozen, value)
    wav = blob[:4] == b"RIFF" and blob[8:12] == b"WAVE"
    mp3 = (
        blob[:3] == b"ID3" or len(blob) > 2 and blob[0] == 255 and blob[1] & 224 == 224
    )
    if not (wav or mp3):
        raise GatewayError("配音接口未返回有效WAV/MP3")
    check(job)
    asset = save_upload(
        job.user,
        SimpleUploadedFile(f"AI配音-{job.id}." + ("wav" if wav else "mp3"), blob),
        "AI配音",
    )
    return {
        "asset_id": asset.id,
        "audio_id": asset.id,
        "source": "tts_api",
        "remote_id": node_state(job).get("task_id", ""),
    }
