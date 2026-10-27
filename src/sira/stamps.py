import gzip
import io

import numpy as np
from astropy.io import fits
from astropy.visualization import ZScaleInterval
from PIL import Image

ZSCALE = ZScaleInterval(contrast=0.25)


def unzip(data: bytes) -> bytes:
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def load(data: bytes) -> np.ndarray:
    with fits.open(io.BytesIO(unzip(data))) as hdul:
        img = next(h.data for h in hdul if h.data is not None)
    return np.nan_to_num(np.asarray(img, dtype=float))


def _stretch(img: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return (img - lo) / ((hi - lo) or 1.0)


def _png(scaled: np.ndarray, upscale: int = 4) -> bytes:
    pic = Image.fromarray(np.flipud((np.clip(scaled, 0, 1) * 255).astype(np.uint8)))
    if upscale > 1:
        pic = pic.resize((pic.width * upscale, pic.height * upscale), Image.NEAREST)
    out = io.BytesIO()
    pic.save(out, format="PNG")
    return out.getvalue()


def to_png(data: bytes, upscale: int = 4) -> bytes:
    img = load(data)
    # same scaling for every stamp, so styling never hints at the answer
    return _png(_stretch(img, *ZSCALE.get_limits(img)), upscale)


def matched(science: bytes, template: bytes, difference: bytes, common: bool = True, upscale: int = 4) -> list[bytes]:
    sci, tpl, dif = load(science), load(template), load(difference)
    lo, hi = ZSCALE.get_limits(sci)
    # ZTF cutouts already share sky level and flux scale, so the science stretch serves the template too
    t_lo, t_hi = (lo, hi) if common else ZSCALE.get_limits(tpl)
    # difference centred on its background: grey is no change, white brighter, black fainter
    mid = np.median(dif)
    d_lo, d_hi = ZSCALE.get_limits(dif)
    half = max(d_hi - mid, mid - d_lo) or 1.0
    return [_png(_stretch(sci, lo, hi), upscale), _png(_stretch(tpl, t_lo, t_hi), upscale),
            _png(0.5 + 0.5 * (dif - mid) / half, upscale)]


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
