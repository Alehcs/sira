import io

import numpy as np
import pytest
from PIL import Image

from sira import alerce, gallery, reader, snapshot

PACKED = reader.PACKAGED / "ZTF25acfgotd_{}.fits.gz"


def cutouts():
    return [PACKED.with_name(PACKED.name.format(k)).read_bytes() for k in reader.KINDS]


def jpeg(spread, level=60):
    rng = np.random.default_rng(0)
    px = np.clip(level + rng.normal(0, spread, (128, 128, 3)), 0, 255).astype(np.uint8)
    px[60:66, 80:100] = (170, 90, 230)
    buf = io.BytesIO()
    Image.fromarray(px).save(buf, format="JPEG")
    return buf.getvalue()


def det(mjd, fid=2, mag=19.0, stamp=True, candid=None, sign="t"):
    return {"mjd": mjd, "fid": fid, "magpsf": mag, "sigmapsf": 0.1, "isdiffpos": sign, "has_stamp": stamp,
            "candid": candid or str(int(mjd * 1000)), "ra": 150.0 + mjd * 1e-6, "dec": -20.0}


def light_curve():
    return {"detections": [det(61330.1, stamp=False, candid="early"), det(61331.2, fid=3, candid="first"),
                           det(61332.3, fid=1), det(61333.4), det(61334.5, sign="f"), det(61335.6, fid=1)],
            "non_detections": [{"mjd": 61329.0, "fid": 2, "diffmaglim": 20.5}]}


@pytest.fixture
def archive(monkeypatch):
    calls = {"curves": [], "stamps": [], "hosts": []}

    def curve(c, oid, fresh=False):
        calls["curves"].append((oid, fresh))
        if oid == "BROKEN":
            raise RuntimeError("archive down")
        return light_curve()

    def stamp(c, oid, candid, kind):
        calls["stamps"].append((oid, candid, kind))
        return cutouts()[reader.KINDS.index(kind)]

    def host(c, ra, dec):
        calls["hosts"].append((ra, dec))
        return jpeg(0 if ra > 200 else 30)

    monkeypatch.setattr(alerce, "lightcurve", curve)
    monkeypatch.setattr(alerce, "stamp", stamp)
    monkeypatch.setattr(snapshot, "_host", host)
    return calls


def test_the_strip_is_the_readers_own_drawing_at_one_pixel_per_ztf_pixel():
    fits = cutouts()
    png, panel = gallery.strip(fits)
    small = np.asarray(Image.open(io.BytesIO(png)))
    seen = np.asarray(Image.open(io.BytesIO(reader.draw(fits, reader.PROTOCOLS["v2"].render))))
    w, h = panel
    assert panel == [63, 63] and small.shape == (h, 3 * w)
    for i in range(3):
        # the reader saw each pixel four times over, with 8 white pixels between panels
        x = i * (4 * w + 8)
        assert np.array_equal(seen[::4, x:x + 4 * w:4], small[:, i * w:(i + 1) * w])


def test_a_flat_legacy_cutout_counts_as_no_image():
    # grey outside the footprint, white on a saturated core, each with a stray streak; a real field has spread
    assert gallery.flat(jpeg(0)) and gallery.flat(jpeg(0, 255)) and not gallery.flat(jpeg(30))


def test_an_object_gets_its_position_points_curve_and_both_images(archive, tmp_path):
    got = gallery.build(["ZTF26aaaaaaa"], tmp_path, fresh={"ZTF26aaaaaaa"})["ZTF26aaaaaaa"]
    assert got["ra"] == pytest.approx(150.0613, abs=1e-3) and got["dec"] == -20.0
    # positive g and r only: the i detection and the negative one do not count
    assert got["points"] == 4 and got["first"] == 61330.1
    assert [r[2] for r in got["curve"]] == ["limit", "det", "det", "det", "det", "det"]
    # the reader's rule: its first detection with a stamp, whatever the band
    assert {c for _, c, _ in archive["stamps"]} == {"first"} and got["taken"] == 61331.2
    assert got["stamps"] == "ZTF26aaaaaaa.png" and got["panel"] == [63, 63] and got["host"] == "ZTF26aaaaaaa.jpg"
    assert (tmp_path / "ZTF26aaaaaaa.png").exists() and (tmp_path / "ZTF26aaaaaaa.jpg").exists()
    assert archive["curves"] == [("ZTF26aaaaaaa", True)]


def test_each_object_fails_on_its_own(archive, tmp_path, monkeypatch):
    def gone(c, oid, candid, kind):
        raise RuntimeError("no stamps")

    monkeypatch.setattr(alerce, "stamp", gone)
    got = gallery.build(["BROKEN", "ZTF26aaaaaaa"], tmp_path)
    assert list(got) == ["ZTF26aaaaaaa"] and "stamps" not in got["ZTF26aaaaaaa"] and got["ZTF26aaaaaaa"]["host"]
    assert ("ZTF26aaaaaaa", False) in archive["curves"]


def test_a_flat_host_is_left_out(archive, tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "_host", lambda c, ra, dec: jpeg(0))
    got = gallery.build(["ZTF26aaaaaaa"], tmp_path)["ZTF26aaaaaaa"]
    assert "host" not in got and got["stamps"] and not (tmp_path / "ZTF26aaaaaaa.jpg").exists()


def test_the_build_stops_fetching_once_its_time_is_up(archive, tmp_path):
    assert gallery.build(["ZTF26aaaaaaa", "ZTF26bbbbbbb"], tmp_path, seconds=-1) == {}
    assert archive["curves"] == []
