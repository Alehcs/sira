// pixel buffer, palette and isometric helpers for the observatory
export const W = 640;
export const H = 360;
export const OX = 320;
export const OY = 218;
export const A = 28;
export const D = 4;
export const RX = 70;
export const RY = 35;
export const HD = 10;
export const SLIT = 50;
export const YDC = OY - 16 - 112;
export const YEQ = YDC - HD;

// the colours, all read from the dome's CSS tokens
const TOKENS = `void n1 w0 w1 w2 w3 w4 w5 f0 f1 f2 f3 x0 x1 x2 x3 m0 m1 m2 m3 m4 d0 d1 d2 d3 d4 d5 wd0 wd1 wd2 wd3 lp0 lp1 lp2
  rd0 rd1 rd2 g0 g1 g2 r0 r1 r2 sc0 sc1 sc2 sc3 pp0 pp1 pp2 ch0 ch1 ch2 gl0 gl1 gl2 ink sk1 sk2 sk3 sk4 hr1 hr2 hr3 hr4 hr5
  c-vig c-lec c-ia c-ibc c-ii c-ins c-fis c-mem c-muse c-dir c-sen c-pro c-lv pants pants2 shoe`.split(/\s+/);

const img = { buf: null };
let PAL = {};

function hex(s) {
  const v = s.trim().replace('#', '');
  const n = parseInt(v.length === 3 ? v.split('').map((c) => c + c).join('') : v, 16);
  return (255 << 24) | ((n & 255) << 16) | (((n >> 8) & 255) << 8) | (n >> 16);
}

export function palette(el) {
  const cs = getComputedStyle(el);
  return Object.fromEntries(TOKENS.map((k) => [k, hex(cs.getPropertyValue(`--${k}`))]));
}

// every drawing call below writes into this buffer with this palette
export function bind(buf, pal) {
  img.buf = buf;
  PAL = pal;
}

export const fill = (c) => img.buf.fill(c);
export const rgb = (r, g, b) => (255 << 24) | (b << 16) | (g << 8) | r;
export const C = (k) => PAL[k];

export function px(x, y, c) {
  x |= 0; y |= 0;
  if (x >= 0 && x < W && y >= 0 && y < H) img.buf[y * W + x] = c;
}

export function rect(x, y, w, h, c) {
  x = Math.round(x); y = Math.round(y); w = Math.round(w); h = Math.round(h);
  for (let j = Math.max(0, y); j < Math.min(H, y + h); j++) {
    for (let i = Math.max(0, x); i < Math.min(W, x + w); i++) img.buf[j * W + i] = c;
  }
}

// mixes a colour over what is already drawn, for glass
function mix(i, c, a) {
  const o = img.buf[i];
  const f = (s) => Math.round(((o >> s) & 255) * (1 - a) + ((c >> s) & 255) * a);
  img.buf[i] = (255 << 24) | (f(16) << 16) | (f(8) << 8) | f(0);
}

export function poly(pts, c, a) {
  let y0 = Infinity, y1 = -Infinity;
  for (const p of pts) { if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
  y0 = Math.max(0, Math.floor(y0)); y1 = Math.min(H, Math.ceil(y1));
  const n = pts.length;
  const xs = [];
  for (let y = y0; y < y1; y++) {
    const cy = y + 0.5;
    xs.length = 0;
    for (let i = 0; i < n; i++) {
      const p = pts[i], q = pts[(i + 1) % n];
      if ((p[1] <= cy && q[1] > cy) || (q[1] <= cy && p[1] > cy)) xs.push(p[0] + ((cy - p[1]) * (q[0] - p[0])) / (q[1] - p[1]));
    }
    xs.sort((p, q) => p - q);
    for (let k = 0; k + 1 < xs.length; k += 2) {
      const xa = Math.max(0, Math.ceil(xs[k] - 0.5)), xb = Math.min(W - 1, Math.floor(xs[k + 1] - 0.5));
      if (a) for (let x = xa; x <= xb; x++) mix(y * W + x, c, a);
      else for (let x = xa; x <= xb; x++) img.buf[y * W + x] = c;
    }
  }
}

export function line(x0, y0, x1, y1, c) {
  x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let e = dx + dy;
  for (;;) {
    px(x0, y0, c);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * e;
    if (e2 >= dy) { e += dy; x0 += sx; }
    if (e2 <= dx) { e += dx; y0 += sy; }
  }
}

// world tiles to screen: +x runs right-down, +y left-down, z is screen pixels up
export const P = (x, y, z) => [OX + 8 * (x - y), OY + 4 * (x + y) - z];
export const quad = (a, b, c, d, col, al) => poly([P(...a), P(...b), P(...c), P(...d)], col, al);
export const floorRect = (x0, y0, x1, y1, z, col, al) => quad([x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z], col, al);
export const wallX = (xw, y0, y1, z0, z1, col, al) => quad([xw, y0, z0], [xw, y1, z0], [xw, y1, z1], [xw, y0, z1], col, al);
export const wallY = (yw, x0, x1, z0, z1, col, al) => quad([x0, yw, z0], [x1, yw, z0], [x1, yw, z1], [x0, yw, z1], col, al);
export const iline = (a, b, col) => { const p = P(...a), q = P(...b); line(p[0], p[1], q[0], q[1], col); };

// a box: top, the face looking left-down (+y) and the face looking right-down (+x)
export function box(x, y, z, w, d, h, top, left, right, edge) {
  wallY(y + d, x, x + w, z, z + h, left);
  wallX(x + w, y, y + d, z, z + h, right);
  floorRect(x, y, x + w, y + d, z + h, top);
  if (edge) {
    iline([x, y + d, z + h], [x + w, y + d, z + h], edge);
    iline([x + w, y, z + h], [x + w, y + d, z + h], edge);
  }
}

// a deterministic hash for flicker and blinking
export function hash(a, b) {
  let h = (a * 374761393 + b * 668265263) | 0;
  h = (h ^ (h >>> 13)) * 1274126177;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
