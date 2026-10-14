"""Upload validation: size, real image decoding, allowed formats, pixel budget."""
from __future__ import annotations

import io
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png")}


@dataclass
class DecodedUpload:
    data: bytes
    image: Image.Image       # fully loaded
    content_type: str
    extension: str
    filename: str | None


def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    data = file.file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Image exceeds {max_bytes // (1024 * 1024)} MB limit")
    return data


def decode_upload(file: UploadFile, max_bytes: int, max_pixels: int, label: str) -> DecodedUpload:
    """Validates by actually decoding the bytes (never trusts filename or client content-type)."""
    data = read_upload(file, max_bytes)
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        if fmt not in ALLOWED_FORMATS:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{label}: only JPEG and PNG images are accepted")
        if probe.size[0] * probe.size[1] > max_pixels:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{label}: image has too many pixels")
        img = Image.open(io.BytesIO(data))
        img.load()  # surfaces truncated / corrupt data now, not later during inference
    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label}: file is not a valid image")
    ctype, ext = ALLOWED_FORMATS[fmt]
    return DecodedUpload(data=data, image=img, content_type=ctype, extension=ext, filename=(file.filename or None))
