from __future__ import annotations

from PIL import Image


class WatermarkRemovalError(RuntimeError):
    pass


def _load_cv2():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - reported through the UI.
        raise WatermarkRemovalError("缺少 OpenCV，请先安装 opencv-python。") from exc
    return cv2, np


def remove_masked_area(
    image: Image.Image,
    mask: Image.Image,
    radius: int = 5,
) -> Image.Image:
    cv2, np = _load_cv2()

    source = image.convert("RGBA")
    mask_l = mask.convert("L")
    if source.size != mask_l.size:
        raise WatermarkRemovalError("修复遮罩尺寸与图片尺寸不一致。")

    source_array = np.array(source)
    mask_array = np.array(mask_l)
    if int(mask_array.max()) == 0:
        raise WatermarkRemovalError("请先涂抹或框选需要修复的水印区域。")

    binary_mask = np.where(mask_array > 0, 255, 0).astype("uint8")
    rgb = source_array[:, :, :3]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    repaired_bgr = cv2.inpaint(
        bgr,
        binary_mask,
        max(1, int(radius)),
        cv2.INPAINT_TELEA,
    )
    repaired_rgb = cv2.cvtColor(repaired_bgr, cv2.COLOR_BGR2RGB)
    output = source_array.copy()
    output[:, :, :3] = repaired_rgb
    return Image.fromarray(output, "RGBA")
