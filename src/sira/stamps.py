import gzip
import io

import numpy as np
from astropy.io import fits
from astropy.visualization import ZScaleInterval
from PIL import Image


def to_png(data: bytes, upscale: int = 4) -> bytes:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    with fits.open(io.BytesIO(data)) as hdul:
        img = next(h.data for h in hdul if h.data is not None)
    img = np.nan_to_num(np.asarray(img, dtype=float))
    # same scaling for every stamp, so styling never hints at the answer
    lo, hi = ZScaleInterval(contrast=0.25).get_limits(img)
    scaled = np.clip((img - lo) / ((hi - lo) or 1.0), 0, 1)
    pic = Image.fromarray(np.flipud((scaled * 255).astype(np.uint8)))
    if upscale > 1:
        pic = pic.resize((pic.width * upscale, pic.height * upscale), Image.NEAREST)
    out = io.BytesIO()
    pic.save(out, format="PNG")
    return out.getvalue()


def side_by_side(pngs: list[bytes], gap: int = 8) -> bytes:
    pics = [Image.open(io.BytesIO(p)) for p in pngs]
    sheet = Image.new("L", (sum(p.width for p in pics) + gap * (len(pics) - 1), max(p.height for p in pics)), 255)
    x = 0
    for pic in pics:
        sheet.paste(pic, (x, 0))
        x += pic.width + gap
    out = io.BytesIO()
    sheet.save(out, format="PNG")
    return out.getvalue()


def zoom(png: bytes, factor: int = 3) -> bytes:
    pic = Image.open(io.BytesIO(png))
    w, h = pic.size
    dx, dy = w // (2 * factor), h // (2 * factor)
    crop = pic.crop((w // 2 - dx, h // 2 - dy, w // 2 + dx, h // 2 + dy)).resize((w, h), Image.NEAREST)
    out = io.BytesIO()
    crop.save(out, format="PNG")
    return out.getvalue()
