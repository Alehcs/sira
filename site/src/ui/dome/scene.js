// places the cast and draws one frame of the observatory from the state of the moment
import { drawCatwalk, drawCatwalkRail, drawControlShell, drawDome, drawGalleryFloor, drawLabShell, drawNight, drawPedestal, drawRailing, wallTops } from './building.js';
import { C, OX, P, RX, YDC, px, rect } from './engine.js';
import { CAST, SKIN, figure, gear, held } from './people.js';
import {
  drawBackConsoles, drawBoards, drawCable, drawDirector, drawForecaster, drawLeVerrier, drawMast, drawMuseBooth, drawMuseGlass,
  drawReader, drawSenior, drawSeniorGlass, drawSkeptics, drawTelescope, slipAt,
} from './props.js';

// where each agent stands (world tiles at a floor height), how it works and how it talks
const SPOTS = {
  lec: { w: [2.3, 4.9, 56], work: 'back', talk: 'front' },
  tia: { w: [1.1, 9, 56], work: 'write', talk: 'front' },
  tibc: { w: [1.1, 14, 56], work: 'write', talk: 'front' },
  tii: { w: [1.1, 19, 56], work: 'write', talk: 'front' },
  muse: { w: [2.5, 24.9, 56], work: 'sit', talk: 'sitfront' },
  ein: { w: [5.3, 2.4, 56], work: 'back', talk: 'front' },
  efi: { w: [9.7, 2.7, 56], work: 'sit', talk: 'sitfront' },
  eme: { w: [14.6, 2.3, 56], work: 'back', talk: 'front' },
  lv: { w: [22.1, 2.8, 56], work: 'sit', talk: 'front', board: [20.6, 1.5, 56] },
  dir: { w: [11.0, 12.2, 0], work: 'sit', talk: 'sitfront' },
  sen: { w: [5.6, 21.6, 0], work: 'sitfront', talk: 'sitfront' },
  pro: { w: [18.5, 4.9, 0], work: 'sit', talk: 'sitfront' },
};
const LOOKOUTS = [[OX - RX - 6, YDC - 1], [OX - RX - 13, YDC - 6]];
const FLIPPED = new Set(['efi', 'eme', 'ein', 'pro']);

function feet(id, st) {
  const s = SPOTS[id];
  const p = P(...(id === 'lv' && !st.asleep && (st.agents.lv || st.chalk > 0) ? s.board : s.w));
  return [Math.round(p[0]), Math.round(p[1])];
}

function poseOf(id, st, t) {
  const s = SPOTS[id], a = st.agents[id];
  if (id === 'lv') {
    if (st.asleep) return 'sleep';
    if (a && a.talk) return 'front';
    if (a && a.think) return Math.floor(t * 3) % 2 ? 'write' : 'back';
    return st.chalk > 0 ? 'back' : 'sit';
  }
  if (a && a.talk) return s.talk;
  if (a && a.think && s.work === 'write') return Math.floor(t * 3 + id.length) % 2 ? 'write' : 'back';
  if (s.work === 'write') return 'back';
  return s.work;
}

function drawAgent(id, st, t) {
  const a = CAST[id];
  const [x, y] = feet(id, st);
  const pose = poseOf(id, st, t);
  const busy = st.agents[id] && st.agents[id].think;
  const seated = pose.startsWith('sit') || pose === 'sleep';
  // breathing: a pixel up and down, faster when busy
  const lift = seated ? 0 : Math.floor(t * (busy ? 2.2 : 1.1) + id.charCodeAt(0) * 0.37) % 2;
  const flip = FLIPPED.has(id);
  figure(pose, x, y, a, flip, lift);
  const front = pose === 'front' || pose === 'sitfront';
  if (a.gear && !(pose === 'sleep' && a.gear === 'tophat') && (front || !['glasses', 'lamp'].includes(a.gear))) {
    gear(a.gear, x, y - lift, a, flip, pose, t);
  }
  if (a.held && front) held(a.held, x + (flip ? -6 : 3), y - (pose === 'front' ? 7 + lift : 5));
  // typing hands when a seated agent is busy
  if (busy && pose === 'sit') {
    const k = Math.floor(t * 8) % 2;
    px(x - 3 + k, y - 5, C(SKIN[a.skin][0]));
    px(x + 2 - k, y - 5, C(SKIN[a.skin][0]));
  }
  return { x, y, top: y - (seated ? 13 : 16) - lift };
}

function drawLookouts(t) {
  return LOOKOUTS.map(([x, y], i) => {
    const a = CAST[i ? 'vig2' : 'vig1'];
    const lift = Math.floor(t * 0.9 + i * 0.5) % 2;
    if (i) {
      // this one points out at the sky
      figure(Math.floor(t * 0.4) % 3 ? 'write' : 'back', x, y, a, true, lift);
      gear(a.gear, x, y - lift, a, true, 'back', t);
    } else {
      figure('front', x, y, a, false, lift);
      gear(a.gear, x, y - lift, a, false, 'front', t);
      // binoculars held up to the eyes
      const yy = y - 14 - lift;
      rect(x - 3, yy, 3, 3, C('ink')); rect(x + 1, yy, 3, 3, C('ink'));
      px(x - 2, yy, C('m3')); px(x + 2, yy, C('m3'));
      px(x, yy + 1, C('m1'));
      px(x - 4, yy + 3, C(SKIN[a.skin][0])); px(x + 4, yy + 3, C(SKIN[a.skin][0]));
    }
    return { x, y, top: y - 17 - lift };
  });
}

// a dotted path from a speaker to whoever it addresses; the dots march toward the listener
function drawPath(a, b, t, colour) {
  const mx = (a[0] + b[0]) / 2, my = Math.min(a[1], b[1]) - 16 - Math.abs(a[0] - b[0]) * 0.08;
  const pts = [];
  let last = null, len = 0;
  for (let i = 0; i <= 240; i++) {
    const u = i / 240;
    const x = (1 - u) * (1 - u) * a[0] + 2 * u * (1 - u) * mx + u * u * b[0];
    const y = (1 - u) * (1 - u) * a[1] + 2 * u * (1 - u) * my + u * u * b[1];
    if (last) len += Math.hypot(x - last[0], y - last[1]);
    pts.push([x, y, len]);
    last = [x, y];
  }
  const phase = (t * 18) % 4;
  let prev = null;
  for (const [x, y, l] of pts) {
    if (l > len - 4) break;
    const k = Math.floor((l - phase) / 4);
    if (k !== prev && (((l - phase) % 4) + 4) % 4 < 1) { px(Math.round(x), Math.round(y), colour); prev = k; }
  }
  // an arrowhead along the last stretch, pointing at the listener
  const [ex, ey] = pts[pts.length - 1], [qx, qy] = pts[pts.length - 12];
  const d = Math.hypot(ex - qx, ey - qy) || 1, ux = (ex - qx) / d, uy = (ey - qy) / d;
  for (let i = 0; i < 4; i++) for (let w = -i; w <= i; w++) px(Math.round(ex - ux * (3 - i) - uy * w), Math.round(ey - uy * (3 - i) + ux * w), colour);
}

// where a path lands on a listener: beside the head, on the speaker's side
function landing(from, h) {
  const s = Math.sign(from.x - h.x) || 1;
  return [h.x + s * 6, h.top + 6];
}

export function frame(t, st) {
  drawNight();
  drawCatwalk();
  drawDome(st.sky);
  drawCatwalkRail();
  const heads = {};
  heads.vig = drawLookouts(t);
  drawMast(t);
  drawPedestal();

  // the control room
  drawControlShell();
  drawBackConsoles(t);
  drawSenior();
  heads.sen = drawAgent('sen', st, t);
  drawSeniorGlass();
  drawDirector(t, st);
  heads.dir = drawAgent('dir', st, t);
  drawForecaster(t, st);
  heads.pro = drawAgent('pro', st, t);

  // the lab gallery
  drawLabShell(st.alarm);
  drawBoards(st);
  drawGalleryFloor();
  drawReader(t, st);
  drawSkeptics(t, st);
  drawLeVerrier(st);
  drawMuseBooth(st);
  for (const id of ['lec', 'ein', 'tia', 'efi', 'tibc', 'eme', 'tii', 'lv']) heads[id] = drawAgent(id, st, t);
  drawMuseGlass();
  heads.muse = drawAgent('muse', st, t);
  drawRailing();
  wallTops(112);
  drawCable(st.pulse);
  drawTelescope(t, st);
  heads.ztf = { x: OX - 2, y: YDC - 36, top: YDC - 40, bx: OX + RX - 6, by: YDC - 44 };
  const sp = slipAt();
  heads.printer = { x: sp[0], y: sp[1], top: sp[1] - 8 };

  for (const e of st.talks) {
    const from = heads[e.who];
    for (const to of e.to) {
      const h = heads[to];
      if (!from || !h || to === e.who) continue;
      drawPath([from.x, from.top - 2], to === 'printer' ? [h.x, h.top] : landing(from, h), t, C('pp2'));
    }
  }
  return heads;
}

// where each name sits under its agent, and which side each bubble opens to so neighbours do not cover each other
export const TAGS = {
  vig: [0, 3], lec: [-12, 3], tia: [0, 3], tibc: [0, 3], tii: [0, 3], muse: [0, 3], ein: [4, 3], efi: [0, 4], eme: [2, 6], lv: [0, 3],
  dir: [0, 3], sen: [0, 3], pro: [0, 3], ztf: [30, -6],
};
export const TWO = new Set(['ein', 'efi', 'eme']);
export const SIDE = { lec: 'l', tia: 'l', tibc: 'l', tii: 'l', muse: 'l', ein: 'r', efi: 'r', eme: 'r', lv: 'r', dir: 'l', sen: 'r', pro: 'l', ztf: 'r' };
export const slip = slipAt;
