"""图片上传与文件安全检查。"""
from __future__ import annotations

import base64
import io

from .conftest import make_label_png


def _upload(client, headers, data: bytes, filename: str, content_type: str = "image/png"):
    return client.post(
        "/api/upload",
        headers=headers,
        data={"file": (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


def test_analyze_base64_png_success(client, auth, image_bytes):
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    resp = client.post(
        "/api/analyze",
        headers=auth,
        json={"image_base64": data_url, "mode": "packaging"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["mode"] == "packaging"
    assert data["record"]["status"] in {"ocr_done", "uploaded"}
    assert data["image"]["mime"] == "image/png"
    assert data["ocr"]["fields"]
    assert data["fields"]


def test_analyze_base64_rejects_invalid_data(client, auth):
    resp = client.post(
        "/api/analyze",
        headers=auth,
        json={"image_base64": "data:image/png;base64,not-base64!!!", "mode": "packaging"},
    )
    assert resp.status_code == 400
    assert "Base64" in resp.get_json()["message"]


def test_analyze_base64_rejects_invalid_mode(client, auth, image_bytes):
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    resp = client.post(
        "/api/analyze",
        headers=auth,
        json={"image_base64": data_url, "mode": "unknown"},
    )
    assert resp.status_code == 400
    assert "mode" in resp.get_json()["message"]


def test_upload_png_success(client, auth, image_bytes):
    resp = _upload(client, auth, image_bytes, "label.png")
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["record"]["status"] == "uploaded"
    assert data["record"]["is_demo"] is False
    assert data["image"]["width"] > 0 and data["image"]["height"] > 0
    assert data["image"]["mime"] == "image/png"
    assert data["image"]["url"].startswith("/api/records/")
    # 记录概览里也要带上尺寸，前端据此提示「分辨率偏低」
    record_image = data["record"]["image"]
    assert record_image["width"] == data["image"]["width"]
    assert record_image["height"] == data["image"]["height"]


def test_upload_jpeg_success(client, auth):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (600, 400), (250, 250, 248)).save(buffer, format="JPEG")
    resp = _upload(client, auth, buffer.getvalue(), "label.jpg", "image/jpeg")
    assert resp.status_code == 201
    assert resp.get_json()["data"]["image"]["mime"] == "image/jpeg"


def test_upload_webp_success(client, auth):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (500, 500), (240, 245, 244)).save(buffer, format="WEBP")
    resp = _upload(client, auth, buffer.getvalue(), "label.webp", "image/webp")
    assert resp.status_code == 201


def test_upload_rejects_fake_image(client, auth):
    resp = _upload(client, auth, b"this is not an image at all", "hack.png", "image/png")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert "图片" in body["message"]


def test_upload_rejects_unsupported_format(client, auth):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), (255, 255, 255)).save(buffer, format="GIF")
    resp = _upload(client, auth, buffer.getvalue(), "label.gif", "image/gif")
    assert resp.status_code == 400


def test_upload_rejects_missing_file(client, auth):
    resp = client.post("/api/upload", headers=auth, data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "未收到图片文件" in resp.get_json()["message"]


def test_upload_rejects_too_large(client, auth):
    # 直接构造 11MB 的伪图片，触发 MAX_CONTENT_LENGTH
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (11 * 1024 * 1024)
    resp = _upload(client, auth, big, "big.png")
    assert resp.status_code == 413
    assert resp.get_json()["success"] is False


def test_upload_requires_login(client, image_bytes):
    resp = _upload(client, {}, image_bytes, "label.png")
    assert resp.status_code == 401


def test_upload_sanitizes_filename(client, auth, image_bytes, app):
    resp = _upload(client, auth, image_bytes, "../../..\\evil path/标签.png")
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    original = data["image"]["original_name"]
    assert "/" not in original and "\\" not in original
    # 磁盘文件名必须是服务端生成的 UUID，不含用户输入
    resp = client.get(f"/api/records/{data['record']['id']}/image", headers=auth)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("image/")


def test_upload_generates_unique_records(client, auth, image_bytes):
    first = _upload(client, auth, image_bytes, "a.png").get_json()["data"]["record"]["id"]
    second = _upload(client, auth, image_bytes, "a.png").get_json()["data"]["record"]["id"]
    assert first != second


def test_upload_rejects_heic_with_actionable_message(client, auth):
    """iPhone 的 HEIC 在服务器无法解码时，要给出可操作的提示，而不是笼统报错。"""
    fake_heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"0" * 64
    resp = client.post(
        "/api/upload",
        headers=auth,
        data={"file": (io.BytesIO(fake_heic), "IMG_0001.HEIC")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    message = resp.get_json()["message"]
    assert "HEIC" in message or "heic" in message
    assert "兼容性最佳" in message or "JPG" in message
