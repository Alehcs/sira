from sira import snapshot

BTS_ROWS = [
    {"oid": "ZTF25ia00001", "name": "SN2025a", "type": "SN Ia", "redshift": 0.05, "peak_mjd": 60800.0, "av": 0.1},
    {"oid": "ZTF25ia00002", "name": "SN2025b", "type": "SN Ia", "redshift": 0.3, "peak_mjd": 60800.0, "av": 0.1},
    {"oid": "ZTF25cc00001", "name": "SN2025c", "type": "SN II", "redshift": 0.02, "peak_mjd": 60800.0, "av": 0.1},
    {"oid": "ZTF24td00001", "name": "TDE2024a", "type": "TDE-H-He", "redshift": 0.07, "peak_mjd": 60500.0, "av": 0.1},
    {"oid": "ZTF19old0001", "name": "SN2019a", "type": "SN Ia", "redshift": 0.05, "peak_mjd": 58700.0, "av": 0.1},
]
MULENS_ROWS = [{"oid": "ZTF20abwxmep", "t0_mjd": 59092.2, "tE": 41.7, "u0": 0.48}]


def test_split_is_stable():
    assert snapshot.split("ZTF25ia00001") == snapshot.split("ZTF25ia00001")
    assert {snapshot.split(f"ZTF{i}") for i in range(50)} == {"dev", "test"}


def test_pick_filters_by_category():
    cases = snapshot.pick(BTS_ROWS, MULENS_ROWS)
    cats = {c["oid"]: c["category"] for c in cases}
    assert cats == {"ZTF25ia00001": "ia", "ZTF25cc00001": "cc", "ZTF24td00001": "rare", "ZTF20abwxmep": "microlensing"}


def test_objects_never_carry_the_answer(tmp_path, monkeypatch):
    lc = {"detections": [{"mjd": 60790.0, "fid": 1, "magpsf": 19.0, "sigmapsf": 0.1, "isdiffpos": 1,
                          "candid": 9, "has_stamp": True, "ra": 10.0, "dec": 5.0}], "non_detections": []}
    monkeypatch.setattr(snapshot.alerce, "lightcurve", lambda c, oid: lc)
    monkeypatch.setattr(snapshot.alerce, "stamp", lambda c, oid, candid, kind: b"")
    monkeypatch.setattr(snapshot.stamps, "to_png", lambda data: b"png")
    monkeypatch.setattr(snapshot, "_host", lambda c, ra, dec: b"jpg")
    case = snapshot.pick(BTS_ROWS, [])[0]
    obj, files = snapshot.ztf_object(None, case, tmp_path)
    text = str(obj)
    assert "SN Ia" not in text and "redshift" not in text and "SN2025" not in text
    assert obj["host"]["predates_event"] is True
    assert len(files) == 4
