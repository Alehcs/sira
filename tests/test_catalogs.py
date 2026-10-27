import pytest

from sira.catalogs import parse_bts, parse_mulens

BTS = """
ZTFID,IAUID,RA,Dec,peakt,peakfilt,peakmag,peakabs,duration,rise,fade,type,redshift,b,A_V
ZTF25aaaaaaa,SN2025abc,01:00:00,+10:00:00,2900.5,g,18.1,-19.2,30,15,15,SN Ia,0.05,-40,0.1
ZTF25bbbbbbb,AT2025xyz,02:00:00,+20:00:00,-,r,18.9,-,-,-,-,-,-,-30,0.2
"""

MULENS = """ZTF_ID,Gaia_alerts,RaDeg,DecDeg,t_0,u_0,t_E,pien,piee,r_s,g_s,chi2/dof,det_eff
ZTF20abwxmep,...,12.9,60.6,9092.74^{+0.88}_{-0.90},-0.48^{+0.06}_{-0.10},41.7^{+5.9}_{-3.1},...,...,20.1,21.6,1229.7/933,0.26
ZTF0527.8+5142,...,81.9,51.7,9445.32,0.05,69.6,...,...,19.3,20.3,1536.1/877,0.38
ZTF20abwxmep,...,12.9,60.6,9093.0,0.5,40.0,...,...,20.1,21.6,1229.7/933,0.26
"""


def test_bts_parses_and_skips_missing_peak():
    rows = parse_bts(BTS)
    assert len(rows) == 1
    r = rows[0]
    assert (r["oid"], r["type"], r["redshift"]) == ("ZTF25aaaaaaa", "SN Ia", 0.05)
    assert r["peak_mjd"] == pytest.approx(2900.5 + 57999.5)
    assert (r["ra"], r["dec"], r["peak_mag"]) == (pytest.approx(15.0), pytest.approx(10.0), 18.1)


def test_negative_declinations_keep_their_sign():
    from sira.catalogs import _deg
    assert _deg("-04:30:00") == pytest.approx(-4.5)
    assert _deg("-00:30:00") == pytest.approx(-0.5)


def test_mulens_keeps_alert_ids_once():
    rows = parse_mulens(MULENS)
    assert [r["oid"] for r in rows] == ["ZTF20abwxmep"]
    assert rows[0]["t0_mjd"] == pytest.approx(9092.74 + 49999.5)
    assert rows[0]["u0"] == pytest.approx(0.48)
    assert (rows[0]["ra"], rows[0]["dec"]) == (12.9, 60.6)
