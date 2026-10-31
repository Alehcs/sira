// equipment, the telescope and the screens that show real data
import { C, D, OX, OY, P, RX, YDC, box, hash, iline, line, poly, px, rect, rgb, wallX, wallY } from './engine.js';

// a box turned to face us: its front and top are plain rectangles
function fbox(u0, u1, v, depth, z, h, front, top, edge) {
  const x0 = OX + 8 * u0, x1 = OX + 8 * u1;
  const yb = OY + 4 * v - z;
  rect(x0, yb - h, x1 - x0, h, front);
  rect(x0, yb - h - Math.round(4 * depth), x1 - x0, Math.round(4 * depth), top);
  if (edge) rect(x0, yb - h, x1 - x0, 1, edge);
  return { x0, x1, top: yb - h, bottom: yb };
}

// image pixels at their native size, values untouched
function pixels(rows, x, y) {
  if (!rows) return;
  for (let j = 0; j < rows.length; j++) for (let i = 0; i < rows[j].length; i++) {
    const [r, g, b] = rows[j][i];
    px(x + i, y + j, rgb(r, g, b));
  }
}

// a small light curve: map(i, j) puts plot cell (i from the left, j from the bottom) on screen
function curve(map, w, h, o) {
  const lf0 = Math.log10(o.f0), lf1 = Math.log10(o.f1);
  const I = (d) => Math.round(((d - o.x0) / (o.x1 - o.x0)) * (w - 1));
  const J = (f) => Math.round(((Math.log10(Math.max(f, o.f0)) - lf0) / (lf1 - lf0)) * (h - 1));
  const put = (i, j, c) => { if (i >= 0 && i < w && j >= 0 && j < h) { const [x, y] = map(i, j); px(x, y, c); } };
  if (o.fan) {
    for (const [d, m, s] of o.fan) {
      const i = I(d);
      for (let j = J(m - 1.645 * s); j <= J(m + 1.645 * s); j++) put(i, j, o.fanColour);
      put(i, J(m), o.fanLine);
    }
  }
  if (o.now != null) for (let j = 0; j < h; j += 2) put(I(o.now), j, o.nowColour);
  for (const p of o.points) put(I(p[0]), J(p[1]), p[2]);
}

// the measurements known at this moment, in their band colours
const pts = (st, bands = 'gr') => st.pts.filter((p) => bands.includes(p[2])).map((p) => [p[0], p[1], C(p[2] === 'g' ? 'g1' : 'r1')]);

// the 48-inch Samuel Oschin Schmidt carrying the ZTF camera
export function drawTelescope(t, st) {
  const cx = OX, base = YDC + 3, axis = YDC - 31;
  // pier and turntable
  rect(cx - 8, base - 12, 16, 12, C('m1'));
  rect(cx - 8, base - 12, 2, 12, C('m2'));
  rect(cx + 5, base - 12, 3, 12, C('m0'));
  rect(cx - 15, base - 17, 30, 5, C('d3'));
  rect(cx - 15, base - 17, 30, 1, C('d5'));
  rect(cx - 15, base - 13, 30, 1, C('m1'));
  // the far arm of the yoke
  rect(cx - 15, axis - 4, 5, base - 17 - axis + 4, C('d3'));
  rect(cx - 15, axis - 4, 1, base - 17 - axis + 4, C('d4'));
  // the tube, tipped toward the slit, outlined
  const dir = [-0.2425, -0.9701], per = [0.9701, -0.2425];
  const at = (k, w) => [cx + dir[0] * k + per[0] * w, axis + dir[1] * k + per[1] * w];
  const band = (k0, k1, w0, w1, c) => poly([at(k0, w0), at(k1, w0), at(k1, w1), at(k0, w1)], c);
  band(-23, 38, -9, 9, C('ink'));
  band(-22, 37, -8, -3, C('d5'));
  band(-22, 37, -3, 3, C('d4'));
  band(-22, 37, 3, 8, C('d3'));
  // the corrector cell at the top and the mirror cell at the bottom
  band(32, 37, -8, 8, C('m2'));
  band(35, 37, -6, 6, C('gl0'));
  band(-22, -17, -8, 8, C('m1'));
  band(-22, -21, -8, 8, C('m0'));
  // the ZTF camera inside the tube, at the Schmidt focus: its housing and status lights
  band(6, 13, -9, 9, C('m0'));
  band(12, 13, -9, 9, C('m2'));
  const [lx, ly] = at(9, -6);
  px(lx, ly, Math.floor(t * 2) % 4 === 0 ? C('g2') : C('g1'));
  const [rx, ry] = at(9, -3);
  px(rx, ry, st.exposing ? C('r1') : C('r0'));
  // the near arm and the declination hub
  rect(cx + 10, axis - 4, 5, base - 17 - axis + 4, C('d4'));
  rect(cx + 10, axis - 4, 1, base - 17 - axis + 4, C('d5'));
  rect(cx + 14, axis - 4, 1, base - 17 - axis + 4, C('d3'));
  rect(cx + 9, axis - 2, 7, 5, C('m2'));
  rect(cx + 11, axis - 1, 3, 3, C('m0'));
  // the camera's cables down the arm
  const [kx, ky] = at(8, 9);
  line(kx, ky, cx + 11, base - 18, C('m0'));
  line(kx + 1, ky + 1, cx + 12, base - 18, C('ink'));
}

// the data cable from the dome down the corner, with a pulse when images arrive
export function drawCable(pulse) {
  const x = OX - 1, y0 = OY - 112, y1 = OY + 12 - 90;
  rect(x, y0, 2, y1 - y0, C('m0'));
  rect(x, y0, 1, y1 - y0, C('m1'));
  if (pulse != null && pulse >= 0 && pulse < 1) rect(x, Math.round(y0 + pulse * (y1 - y0)), 2, 3, C('g2'));
}

// the reader: the plate viewer in the corner and the blink comparator
export function drawReader(t, st) {
  const z = 56, h = 36;
  poly([P(0, 0, z + h), P(3, 0, z + h), P(0, 3, z + h)], C('m2'));
  rect(OX - 24, OY + 12 - z - h, 48, h, C('m1'));
  rect(OX - 24, OY + 12 - z - h, 48, 1, C('m3'));
  rect(OX - 24, OY + 12 - z - 4, 48, 4, C('m0'));
  // the lightbox: the blink plate flips between science and reference, beside the difference
  const y = OY + 12 - z - h + 4;
  rect(OX - 21, y - 1, 42, 19, C('ink'));
  const blink = st.blinking ? Math.floor(t * 2.5) % 2 : 0;
  pixels(st.stamps[blink], OX - 20, y);
  pixels(st.stamps[2], OX + 3, y);
  rect(OX - 20 + (blink ? 9 : 0), y + 18, 8, 1, blink ? C('lp1') : C('g1'));
  px(OX - 22, y + 24, C('m3')); px(OX + 20, y + 24, C('m3'));
  // the blink comparator on its bench along the left wall
  box(0, 3.5, z, 1.5, 2.2, 11, C('wd2'), C('wd1'), C('wd0'));
  box(0.2, 3.9, z + 11, 1.0, 1.4, 7, C('m2'), C('m1'), C('m0'));
  box(0.4, 4.3, z + 18, 0.5, 0.5, 4, C('m3'), C('m2'), C('m1'));
  const ep = P(1.2, 4.6, z + 20);
  px(ep[0], ep[1], C('ink')); px(ep[0] + 1, ep[1], C('m3'));
  const lamp = P(0.7, 5.3, z + 12);
  px(lamp[0], lamp[1], st.blinking && Math.floor(t * 2.5) % 2 ? C('lp2') : C('lp0'));
}

// the theorists' three chalkboards on the left wall
export const BOARDS = { tia: 7, tibc: 12, tii: 17 };

const boardMap = (y1, z0) => (i, j) => { const p = P(0.02, y1 - i / 8, z0 + j); return [p[0] - 1, p[1]]; };

export function drawBoards(st) {
  for (const [id, y0] of Object.entries(BOARDS)) {
    const z0 = 56 + 17;
    wallX(0.02, y0 - 0.25, y0 + 4.25, z0 - 2, z0 + 23, C('wd1'));
    wallX(0.02, y0, y0 + 4, z0, z0 + 21, C('ch0'));
    iline([0.3, y0, z0 - 2], [0.3, y0 + 4, z0 - 2], C('m2'));
    const map = boardMap(y0 + 4, z0);
    // the measurements, and under them this hypothesis' share of the voice as a chalk bar
    curve((i, j) => map(i + 2, j + 8), 28, 12, { ...st.range, points: pts(st) });
    const n = Math.round((st.weights[st.seats[id]] || 0) * 28);
    for (let i = 0; i < 28; i++) for (let j = 2; j < 5; j++) {
      const [x, y] = map(i + 2, j);
      px(x, y, i < n ? C('ch2') : C('ch1'));
    }
  }
}

// Muse alone: a booth behind glass at the far end of the left gallery
export function drawMuseBooth(st) {
  const z = 56;
  box(0, 23, z, 1.4, 3.6, 11, C('wd2'), C('wd1'), C('wd0'));
  // the monitor faces the room and shows the same light curve the team sees
  box(0.15, 24, z + 11, 0.4, 2.2, 14, C('m1'), C('m1'), C('m0'));
  wallX(0.56, 24.15, 26.05, z + 13, z + 24, C('sc1'));
  const map = (i, j) => P(0.58, 24.2 + i / 8, z + 13 + j);
  curve(map, 15, 10, { ...st.range, now: st.now, nowColour: C('sc3'), points: pts(st) });
  box(0.4, 23.3, z + 11, 0.5, 0.5, 1, C('pp2'), C('pp1'), C('pp0'));
  box(2.0, 24.4, z, 1.0, 1.0, 6, C('m1'), C('m0'), C('m0'));
}

export function drawMuseGlass() {
  const z = 56;
  wallY(22.2, 0, D, z, z + 30, C('gl1'), 0.22);
  iline([0, 22.2, z + 30], [D, 22.2, z + 30], C('m2'));
  iline([0, 22.2, z + 29], [D, 22.2, z + 29], C('m1'));
  iline([D, 22.2, z], [D, 22.2, z + 30], C('m2'));
  iline([1.2, 22.2, z + 24], [2.4, 22.2, z + 6], C('gl1'));
}

// the three skeptics along the right wall
export function drawSkeptics(t, st) {
  const z = 56;
  // instrument: two racks with blinking lights
  for (const x0 of [3, 4.6]) {
    box(x0, 0, z, 1.4, 1.3, 34, C('m1'), C('m0'), C('m1'));
    for (let k = 0; k < 6; k++) {
      const p = P(x0 + 0.2, 1.31, z + 30 - k * 5);
      rect(p[0], p[1], 9, 1, C('x0'));
      const on = hash(Math.floor(t * 3) + k * 7, x0 * 10) > (st.instrument ? 0.35 : 0.7);
      px(p[0] + 2, p[1] + 2, on ? C(k % 3 ? 'g1' : 'lp1') : C('g0'));
      px(p[0] + 4, p[1] + 3, hash(Math.floor(t * 4), k + x0) > 0.5 ? C('r1') : C('r0'));
    }
  }
  // physics: a workstation whose monitor shows the sealed physics forecast and the points
  box(8, 0, z, 3.2, 1.4, 11, C('wd2'), C('wd1'), C('wd0'));
  box(8.4, 0.2, z + 11, 2.4, 0.35, 15, C('m1'), C('m1'), C('m0'));
  wallY(0.56, 8.55, 10.65, z + 13, z + 25, C('sc1'));
  const map = (i, j) => P(8.6 + i / 8, 0.58, z + 13 + j);
  curve(map, 16, 11, { ...st.range, fan: st.old, fanColour: C('sc3'), fanLine: C('r0'), now: st.now, nowColour: C('sc2'), points: pts(st, 'r') });
  box(9.2, 2.2, z, 1.0, 1.0, 6, C('m1'), C('m0'), C('m0'));
  // memory: card catalogue drawers
  box(13, 0, z, 3.2, 1.2, 20, C('wd2'), C('wd1'), C('wd0'));
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) {
    const p = P(13.2 + c * 0.78, 1.21, z + 17 - r * 4.5);
    rect(p[0], p[1] - 2, 5, 1, C('wd3'));
    px(p[0] + 2, p[1] - 1, C('m3'));
  }
  if (st.drawer) box(14.0, 1.2, z + 8, 0.7, 0.9, 3, C('wd3'), C('wd2'), C('wd1'));
}

// Le Verrier: chalkboard, desk and archive at the far right
export function drawLeVerrier(st) {
  const z = 56;
  const y0 = 0.02, x0 = 18.4, z0 = z + 18;
  wallY(y0, x0 - 0.25, x0 + 6.25, z0 - 2, z0 + 28, C('wd1'));
  wallY(y0, x0, x0 + 6, z0, z0 + 26, C('ch0'));
  const map = (i, j) => { const p = P(x0 + i / 8, y0, z0 + 1 + j); return [p[0] + 1, p[1]]; };
  if (st.chalk > 0 && st.lens) {
    // the lens he proposed, drawn in chalk over the old forecast and the measured points
    const o = { x0: 18, x1: 34, f0: 60, f1: 3000 };
    const lens = st.lens.slice(0, Math.max(2, Math.round(st.chalk * st.lens.length)));
    if (st.rival) curve(map, 46, 23, { ...o, points: st.rival.map((p) => [p[0], p[1], C('ch1')]) });
    const J = (m) => Math.round(((Math.log10(Math.min(m, o.f1)) - Math.log10(o.f0)) / (Math.log10(o.f1) - Math.log10(o.f0))) * 22);
    let prev = null;
    for (const [d, m] of lens) {
      const i = Math.round(((d - o.x0) / (o.x1 - o.x0)) * 45), j = J(m);
      if (prev) {
        for (let k = 0; k <= 8; k++) {
          const [x, y] = map(Math.round(prev[0] + ((i - prev[0]) * k) / 8), Math.round(prev[1] + ((j - prev[1]) * k) / 8));
          px(x, y, C('ch2'));
        }
      }
      prev = [i, j];
    }
    curve(map, 46, 23, { ...o, points: pts(st, 'r').map((p) => [p[0], p[1], C('ch2')]) });
  }
  iline([x0, y0 + 0.3, z0 - 1], [x0 + 6, y0 + 0.3, z0 - 1], C('m2'));
  // archive shelves
  box(25.2, 0, z, 2.4, 1.1, 40, C('wd1'), C('wd0'), C('wd1'));
  for (let r = 0; r < 4; r++) {
    for (let k = 0; k < 9; k++) {
      const p = P(25.35 + k * 0.25, 1.11, z + 6 + r * 9);
      rect(p[0], p[1] - 6, 1, 6, C(['rd0', 'pp0', 'g0', 'wd3', 'm2', 'r0'][(k * 7 + r * 3) % 6]));
    }
  }
  // his desk, where he sleeps until the sky surprises the team
  box(20.4, 0.5, z, 3.0, 1.3, 11, C('wd2'), C('wd1'), C('wd0'));
  box(21.0, 0.8, z + 11, 0.9, 0.6, 1, C('pp2'), C('pp1'), C('pp0'));
  if (st.asleep) {
    // his top hat rests on the desk
    const p = P(22.8, 1.0, z + 11);
    rect(p[0] - 2, p[1] - 1, 5, 1, C('ink'));
    rect(p[0] - 1, p[1] - 4, 3, 3, C('ink'));
    rect(p[0] - 1, p[1] - 2, 3, 1, C('rd0'));
  }
  box(21.6, 2.3, z, 1.0, 1.0, 6, C('m1'), C('m0'), C('m0'));
  // a reading lamp on the desk
  box(23.0, 0.7, z + 11, 0.3, 0.3, 8, C('m1'), C('m1'), C('m0'));
  const l = P(23.15, 0.85, z + 19);
  rect(l[0] - 3, l[1] - 1, 6, 2, C('lp1'));
  rect(l[0] - 2, l[1] + 1, 4, 1, C('lp2'));
}

// the control room's low consoles along the back walls, half under the gallery
export function drawBackConsoles(t) {
  for (let x = 6; x < 14; x += 2) {
    box(x, 0, 0, 1.8, 1.3, 14, C('m1'), C('m0'), C('m1'));
    wallY(1.31, x + 0.25, x + 1.55, 6, 12, C('sc1'));
    const p = P(x + 0.5, 1.31, 4);
    px(p[0], p[1], hash(Math.floor(t * 2) + x, 3) > 0.5 ? C('g1') : C('g0'));
    px(p[0] + 3, p[1] + 1, hash(Math.floor(t * 3) + x, 5) > 0.6 ? C('lp1') : C('lp0'));
  }
  for (let y = 6; y < 14; y += 2) {
    box(0, y, 0, 1.3, 1.8, 14, C('m1'), C('m1'), C('m0'));
    wallX(1.31, y + 0.25, y + 1.55, 6, 12, C('sc1'));
    const p = P(1.31, y + 1.2, 4);
    px(p[0], p[1], hash(Math.floor(t * 2) + y, 7) > 0.5 ? C('g1') : C('g0'));
  }
}

function screen(x, y, w, h) {
  rect(x - 2, y - 2, w + 4, h + 4, C('m0'));
  rect(x - 2, y - 2, w + 4, 1, C('m2'));
  rect(x, y, w, h, C('sc0'));
}

// the director's console faces us: a long desk, a big screen and two side screens
export function drawDirector(t, st) {
  const v = 20.4;
  const yb = OY + 4 * v;
  const sx = OX - 22, sy = yb - 50, sw = 44, sh = 28;
  rect(OX - 2, sy + sh + 2, 4, yb - (sy + sh) - 4, C('m0'));
  screen(sx, sy, sw, sh);
  curve((i, j) => [sx + 1 + i, sy + sh - 2 - j], sw - 2, sh - 3,
    { ...st.range, fan: st.fan, fanColour: C('sc3'), fanLine: C('r0'), now: st.now, nowColour: C('m2'), points: pts(st) });
  // left screen: each hypothesis' share of the voice
  const lx = OX - 49, ly = yb - 38, lw = 21, lh = 15;
  rect(lx + 9, ly + lh + 2, 3, yb - (ly + lh) - 4, C('m0'));
  screen(lx, ly, lw, lh);
  st.voices.slice(0, 5).forEach(([h, w], k) => rect(lx + 1, ly + 2 + k * 3, Math.max(1, Math.round(w * (lw - 2))), 2, h === 'null' ? C('m2') : C('m4')));
  // right screen: what the telescope sees, the same real pixels as the slit
  const rx = OX + 28, ry = yb - 38;
  rect(rx + 9, ry + 17, 3, yb - ry - 19, C('m0'));
  screen(rx, ry, 21, 15);
  pixels(st.sky && st.sky.slice(18, 33).map((row) => row.slice(6, 27)), rx, ry);
  const desk = fbox(-6.5, 6.5, v + 1.6, 1.6, 0, 11, C('m1'), C('m2'), C('m3'));
  rect(desk.x0, desk.top + 4, desk.x1 - desk.x0, 1, C('m0'));
  for (let k = 0; k < 12; k++) px(desk.x0 + 8 + k * 7, desk.top - 3, hash(Math.floor(t * 2), k) > 0.45 ? C(k % 4 ? 'lp1' : 'g1') : C('m0'));
  box(10.4, 11.6, 0, 1.2, 1.2, 7, C('m1'), C('m0'), C('m0'));
}

// the senior's glass office: shelves, an armchair, a lamp and a side table
export function drawSenior() {
  const z = 0;
  box(0, 16.6, z, 1.0, 7.6, 30, C('wd1'), C('wd0'), C('wd1'));
  for (let r = 0; r < 3; r++) for (let k = 0; k < 26; k++) {
    const p = P(1.01, 16.8 + k * 0.28, z + 6 + r * 9);
    rect(p[0], p[1] - 6, 1, 6, C(['rd0', 'pp0', 'g0', 'wd3', 'm2', 'r0', 'pp1'][(k * 5 + r * 2) % 7]));
  }
  const lp = P(2.6, 23.4, z);
  rect(lp[0], lp[1] - 22, 1, 22, C('m2'));
  rect(lp[0] - 2, lp[1] - 25, 5, 3, C('lp1'));
  rect(lp[0] - 1, lp[1] - 22, 3, 1, C('lp2'));
  box(4.2, 20.0, z, 1.8, 1.8, 7, C('rd0'), C('rd0'), C('rd0'));
  box(4.2, 20.0, z, 0.5, 1.8, 14, C('rd1'), C('rd0'), C('rd0'));
  box(4.2, 20.0, z, 1.8, 0.4, 10, C('rd1'), C('rd0'), C('rd0'));
  box(6.9, 23.0, z, 1.0, 1.0, 6, C('wd2'), C('wd1'), C('wd0'));
  box(7.0, 23.1, z + 6, 0.6, 0.7, 2, C('rd1'), C('rd0'), C('rd0'));
}

export function drawSeniorGlass() {
  const z = 0, h = 30, X1 = 8.6, Y0 = 16.2, Y1 = 25.4;
  wallY(Y0, 1, X1, z, z + h, C('gl1'), 0.12);
  wallX(X1, Y0, Y1, z, z + h, C('gl1'), 0.18);
  wallY(Y1, 0, X1, z, z + h, C('gl1'), 0.18);
  for (const [a, b] of [[[X1, Y0, z], [X1, Y0, z + h]], [[X1, Y1, z], [X1, Y1, z + h]], [[0, Y1, z], [0, Y1, z + h]],
    [[X1, Y0, z + h], [X1, Y1, z + h]], [[0, Y1, z + h], [X1, Y1, z + h]], [[1, Y0, z + h], [X1, Y0, z + h]], [[X1, 20.8, z], [X1, 20.8, z + h]]]) iline(a, b, C('gl2'));
  iline([X1, 17.0, z + 26], [X1, 18.2, z + 8], C('gl1'));
  iline([2.6, Y1, z + 26], [3.8, Y1, z + 8], C('gl1'));
  iline([X1, 22.4, z], [X1, 22.4, z + 24], C('gl1'));
}

export const slipAt = () => P(20.7, 3.2, 17);

// the forecaster's desk: the telegraph key and the timestamp printer with its slip
export function drawForecaster(t, st) {
  const z = 0;
  box(16, 2.4, z, 6, 1.6, 11, C('wd2'), C('wd1'), C('wd0'));
  box(16.6, 2.8, z + 11, 1.0, 0.7, 1, C('wd3'), C('wd1'), C('wd0'));
  const down = st.keying && Math.floor(t * 9) % 2 === 0;
  const k = P(17.1, 3.15, z + 13 - (down ? 1 : 0));
  rect(k[0] - 3, k[1], 6, 1, C('lp0'));
  px(k[0] + 3, k[1] - 1, C('ink'));
  iline([16.6, 2.9, z + 12], [16.6, 0.05, z + 34], C('m0'));
  box(20, 2.7, z + 11, 1.5, 1.0, 6, C('m2'), C('m1'), C('m0'));
  const p = slipAt();
  if (st.slip > 0) {
    const n = Math.round(st.slip * 10);
    rect(p[0] - 11, p[1] - n, 22, n, C('pp2'));
    rect(p[0] - 11, p[1] - 1, 22, 1, C('pp0'));
  }
  rect(p[0] - 7, p[1], 14, 1, C('ink'));
  px(p[0] + 5, p[1] + 2, st.slip >= 1 ? C('g1') : C('m0'));
  box(21.6, 2.6, z + 11, 0.3, 0.3, 9, C('m1'), C('m1'), C('m0'));
  const l = P(21.75, 2.75, z + 21);
  rect(l[0] - 2, l[1] - 1, 5, 2, C('lp1'));
  box(18.0, 4.4, z, 1.0, 1.0, 6, C('m1'), C('m0'), C('m0'));
}

// a mast on the right catwalk with a spinning anemometer
export function drawMast(t) {
  const x = OX + RX + 9, y = YDC - 6;
  rect(x, y - 30, 1, 30, C('m2'));
  const f = Math.floor(t * 8) % 3;
  const cups = [[-3, 0], [2, -1], [1, 2]];
  rect(x - 3, y - 31, 7, 1, C('m3'));
  for (let i = 0; i < 3; i++) {
    const [dx, dy] = cups[(i + f) % 3];
    px(x + dx, y - 32 + dy, C('m4'));
  }
  rect(x - 1, y - 36, 3, 1, C('m3'));
  px(x + 2, y - 37, C('m3'));
}
