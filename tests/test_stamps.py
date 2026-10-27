import gzip
import io

import numpy as np
from astropy.io import fits
from PIL import Image

from sira.stamps import to_png


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
