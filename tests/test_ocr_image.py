from PIL import Image
import io

from borrar.ocr_utils import prepare_image_for_ocr


def test_prepare_image_for_ocr_returns_numpy_array():
    buffer = io.BytesIO()
    Image.new("RGB", (200, 80), "white").save(buffer, format="PNG")
    buffer.seek(0)

    image_array = prepare_image_for_ocr(buffer)

    assert image_array.shape[0] > 0
    assert image_array.shape[1] > 0
    assert image_array.shape[2] == 3
