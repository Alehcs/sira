import gzip
import io

import numpy as np
from astropy.io import fits
from PIL import Image

from sira.stamps import side_by_side, to_png, zoom


def fits_bytes(data, compress=False):
    buf = io.BytesIO()
    fits.PrimaryHDU(data).writeto(buf)
    raw = buf.getvalue()
    return gzip.compress(raw) if compress else raw


def test_png_size_and_determinism():
    data = np.random.default_rng(0).normal(100, 5, (63, 63))
    data[30, 30] = 400
    a = to_png(fits_bytes(data))
    assert a == to_png(fits_bytes(data))
    assert Image.open(io.BytesIO(a)).size == (252, 252)


def test_gzip_and_nan_are_handled():
    data = np.ones((63, 63))
    data[0, 0] = np.nan
    png = to_png(fits_bytes(data, compress=True), upscale=1)
    assert Image.open(io.BytesIO(png)).size == (63, 63)


def test_side_by_side_keeps_panels_apart():
    panel = to_png(fits_bytes(np.zeros((63, 63))))
    sheet = Image.open(io.BytesIO(side_by_side([panel] * 3)))
    assert sheet.size == (3 * 252 + 2 * 8, 252)
    assert sheet.getpixel((252, 10)) == 255


def test_zoom_magnifies_the_centre():
    data = np.zeros((63, 63))
    data[31, 31] = 100
    big = Image.open(io.BytesIO(zoom(to_png(fits_bytes(data)))))
    assert big.size == (252, 252)
    assert big.getpixel((126, 126)) == 255 and big.getpixel((10, 10)) == 0
