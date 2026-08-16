from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image


def prepare_image_for_ocr(image: Any):
    """Convierte la imagen a un array NumPy compatible con EasyOCR."""
    if isinstance(image, Image.Image):
        img = image.convert("RGB")
    elif hasattr(image, "read"):
        image.seek(0)
        img = Image.open(image).convert("RGB")
    elif isinstance(image, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image)).convert("RGB")
    else:
        raise TypeError("La imagen debe ser un objeto PIL.Image, un buffer o bytes")

    return np.asarray(img)
