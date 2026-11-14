from app.api.routes import _has_valid_file_signature


def test_accepts_jpeg_signature():
    assert _has_valid_file_signature(b"\xff\xd8\xff\xe0sample", "image/jpeg")


def test_accepts_png_signature():
    assert _has_valid_file_signature(b"\x89PNG\r\n\x1a\nsample", "image/png")


def test_accepts_webp_signature():
    assert _has_valid_file_signature(b"RIFF\x08\x00\x00\x00WEBPdata", "image/webp")


def test_rejects_mismatched_mime_and_signature():
    assert not _has_valid_file_signature(b"plain text", "image/jpeg")
    assert not _has_valid_file_signature(b"\xff\xd8\xff", "image/png")


def test_accepts_video_signatures():
    assert _has_valid_file_signature(b"\x00\x00\x00\x18ftypisom", "video/mp4")
    assert _has_valid_file_signature(b"\x1a\x45\xdf\xa3webm", "video/webm")
