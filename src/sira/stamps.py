import gzip
import io

import numpy as np
from astropy.io import fits
from astropy.visualization import ZScaleInterval
from PIL import Image

ZSCALE = ZScaleInterval(contrast=0.25)


def unzip(data: bytes) -> bytes:
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def _read(data: bytes) -> np.ndarray:
    with fits.open(io.BytesIO(unzip(data))) as hdul:
        return np.asarray(next(h.data for h in hdul if h.data is not None), dtype=float)


def load(data: bytes) -> np.ndarray:
    return np.nan_to_num(_read(data))


def _split(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    img = _read(data)
    # ZTF marks masked pixels with NaN or -3.4e38
    good = np.isfinite(img) & (np.abs(img) < 1e30)
    return np.where(good, img, 0.0), good


def _limits(img: np.ndarray, good: np.ndarray) -> tuple[float, float]:
    return ZSCALE.get_limits(img[good]) if good.sum() > 10 else (0.0, 1.0)


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
    (sci, s_ok), (tpl, t_ok), (dif, d_ok) = _split(science), _split(template), _split(difference)
    # masked pixels stay out of every stretch and get a fixed shade, so a mask never rescales the image
    lo, hi = _limits(sci, s_ok)
    # ZTF cutouts already share sky level and flux scale, so the science stretch serves the template too
    t_lo, t_hi = (lo, hi) if common else _limits(tpl, t_ok)
    # difference centred on its background: grey is no change, white brighter, black fainter
    mid = float(np.median(dif[d_ok])) if d_ok.any() else 0.0
    d_lo, d_hi = _limits(dif, d_ok)
    half = max(d_hi - mid, mid - d_lo) or 1.0
    return [_png(np.where(s_ok, _stretch(sci, lo, hi), 0.0), upscale),
            _png(np.where(t_ok, _stretch(tpl, t_lo, t_hi), 0.0), upscale),
            _png(np.where(d_ok, 0.5 + 0.5 * (dif - mid) / half, 0.5), upscale)]


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
