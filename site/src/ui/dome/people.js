// the agents as small pixel figures: templates, colours and accessories
import { C, px, rgb } from './engine.js';

// h hair, H hair shade, s skin, S skin shade, e eye, c coat, C coat shade, l coat light, w shirt, p trousers, P trousers shade, b shoes
const SPRITES = {
  front: [
    '..hhhh..',
    '.hhhhhh.',
    '.hhssshH',
    '.hsesesH',
    '..sssS..',
    '..wSSw..',
    '.lccwccC',
    'lcccwcCC',
    'lccccCCC',
    'scccccCS',
    '.ccccCC.',
    '.ccccCC.',
    '..pppP..',
    '..pp.P..',
    '..pp.P..',
    '.bbb.bb.',
  ],
  back: [
    '..hhhh..',
    '.hhhhhh.',
    '.hhhhhhH',
    '.hhhhhHH',
    '..hhHH..',
    '..sSSS..',
    '.ccccccC',
    'lccccCCC',
    'lccccCCC',
    'scccccCS',
    '.cccccC.',
    '.cccCCC.',
    '..pppP..',
    '..pp.P..',
    '..pp.P..',
    '.bbb.bb.',
  ],
  // back view, right arm raised to a board
  write: [
    '..hhhh..s',
    '.hhhhhh.c',
    '.hhhhhhHc',
    '.hhhhhHHc',
    '..hhHH.c.',
    '..sSSScc.',
    '.cccccCC.',
    'lccccCCC.',
    'lccccCC..',
    'sccccCC..',
    '.cccccC..',
    '.cccCCC..',
    '..pppP...',
    '..pp.P...',
    '..pp.P...',
    '.bbb.bb..',
  ],
  // seated, back to us, hands forward on a desk
  sit: [
    '..hhhh..',
    '.hhhhhh.',
    '.hhhhhhH',
    '.hhhhhHH',
    '..hhHH..',
    '..sSSS..',
    '.ccccccC',
    'lcccccCC',
    'lccccCCC',
    '.cccccC.',
    '.ppppPP.',
    '.pp..PP.',
    '.bb..bb.',
  ],
  // seated, facing us
  sitfront: [
    '..hhhh..',
    '.hhhhhh.',
    '.hhssshH',
    '.hsesesH',
    '..sssS..',
    '..wSSw..',
    '.lccwccC',
    'lcccwcCC',
    'lsccccSC',
    '.ppppPP.',
    '.ppppPP.',
    '.pp..PP.',
    '.bb..bb.',
  ],
  // asleep on the desk: head down on folded arms, seen from behind
  sleep: [
    '........',
    '........',
    '........',
    '........',
    '..hhhh..',
    '.hhhhhhH',
    'scccccCs',
    'lccccCCC',
    'lccccCCC',
    '.cccccC.',
    '.ppppPP.',
    '.pp..PP.',
    '.bb..bb.',
  ],
};

// hair styles change the top rows
const HAIR = {
  short: null,
  long: ['..hhhh..', '.hhhhhh.', 'hhhssshH', 'hhsesesH', 'hhsssShH', 'h.wSSw.H'],
  bald: ['..SSSS..', '.SssssS.', '.hsssssH', '.hsesesH'],
  bun: ['...hh...', '..hhhh..', '.hhhhhh.', '.hhssshH', '.hsesesH'],
};

export const SKIN = { 1: ['sk1', 'sk2'], 2: ['sk2', 'sk3'], 3: ['sk3', 'sk4'], 4: ['sk4', 'sk4'] };

function shade(c, k) {
  // a darker or lighter step of a palette colour, used for coat shading
  const r = c & 255, g = (c >> 8) & 255, b = (c >> 16) & 255;
  const f = (v) => Math.max(0, Math.min(255, Math.round(k > 1 ? v + (255 - v) * (k - 1) : v * k)));
  return rgb(f(r), f(g), f(b));
}

function colours(a) {
  const coat = C(a.coat);
  const [s, S] = SKIN[a.skin].map(C);
  return {
    h: C(a.hair), H: shade(C(a.hair), 0.7), s, S, e: C('ink'),
    c: coat, C: shade(coat, 0.72), l: shade(coat, 1.22), w: C('pp2'),
    p: C(a.pants || 'pants'), P: C('pants2'), b: C('shoe'),
  };
}

// draws a template with its feet at (x, y); flip mirrors it; a 1 px outline goes where the figure meets the background
export function figure(name, x, y, a, flip, lift = 0) {
  let rows = SPRITES[name].slice();
  const hair = HAIR[a.style];
  if (hair && (name === 'front' || name === 'sitfront')) rows = hair.concat(rows.slice(hair.length));
  if (a.style === 'bald' && name !== 'front' && name !== 'sitfront') rows = ['..SSSS..', '.SSSSSS.', '.ShhhhSS'].concat(rows.slice(3));
  if (a.style === 'long' && (name === 'back' || name === 'write' || name === 'sit')) rows = rows.map((r, i) => (i >= 2 && i <= 5 ? 'h' + r.slice(1, 7).replace(/[sS]/g, 'h') + 'H' + r.slice(8) : r));
  if (a.style === 'bun' && name !== 'front' && name !== 'sitfront') rows = ['...hh...', '..hhhh..'].concat(rows.slice(1, 3), rows.slice(4));
  const col = colours(a);
  const h = rows.length, w = Math.max(...rows.map((r) => r.length));
  const x0 = Math.round(x - 4), y0 = Math.round(y - h - lift);
  const at = (i, j) => {
    if (j < 0 || j >= h) return '.';
    const r = rows[j];
    const k = flip ? 7 - i : i;
    return k >= 0 && k < r.length ? r[k] : '.';
  };
  for (let j = -1; j <= h; j++) {
    for (let i = -1; i <= w; i++) {
      const ch = at(i, j);
      if (ch !== '.') { px(x0 + i, y0 + j, col[ch]); continue; }
      if (at(i - 1, j) !== '.' || at(i + 1, j) !== '.' || at(i, j - 1) !== '.' || at(i, j + 1) !== '.') px(x0 + i, y0 + j, C('ink'));
    }
  }
  return { x: x0, y: y0, w, h };
}

// accessories drawn over a figure, in figure coordinates (feet at x, y)
export function gear(kind, x, y, a, flip, pose, t) {
  const X = (i) => Math.round(x - 4 + (flip ? 7 - i : i));
  const Y = (j) => Math.round(y - (pose === 'sit' || pose === 'sitfront' || pose === 'sleep' ? 13 : 16) + j);
  const d = (i, j, c) => px(X(i), Y(j), C(c));
  if (kind === 'tophat') {
    for (let i = 1; i <= 6; i++) d(i, 0, 'ink');
    for (let j = -4; j <= -1; j++) for (let i = 2; i <= 5; i++) d(i, j, i === 5 ? 'm0' : 'ink');
    for (let i = 2; i <= 5; i++) d(i, -1, 'rd0');
  } else if (kind === 'beret') {
    for (let i = 1; i <= 6; i++) d(i, 0, a.extra);
    for (let i = 2; i <= 5; i++) d(i, -1, a.extra);
    d(4, -2, a.extra);
  } else if (kind === 'beanie') {
    for (let i = 1; i <= 6; i++) { d(i, 0, a.extra); d(i, 1, a.extra); }
    for (let i = 2; i <= 5; i++) d(i, -1, a.extra);
  } else if (kind === 'phones') {
    for (let i = 1; i <= 6; i++) d(i, -1, 'm1');
    d(0, 0, 'm1'); d(7, 0, 'm1');
    d(0, 1, 'm0'); d(0, 2, 'm0'); d(7, 1, 'm0'); d(7, 2, 'm0');
  } else if (kind === 'headset') {
    for (let i = 1; i <= 6; i++) d(i, -1, 'm2');
    d(0, 1, 'm1'); d(0, 2, 'm1'); d(1, 4, 'm1'); d(2, 4, 'm2');
  } else if (kind === 'lamp') {
    d(3, 1, 'lp2'); d(4, 1, 'lp2'); d(2, 1, 'm1'); d(5, 1, 'm1');
  } else if (kind === 'glasses') {
    d(2, 3, 'm3'); d(4, 3, 'm3'); d(3, 3, 'm2');
  } else if (kind === 'scarf') {
    for (let i = 1; i <= 6; i++) d(i, 5, a.extra);
    d(5, 6, a.extra); d(5, 7, a.extra);
  }
}

// small objects held in a hand: book, loupe, cards, mug, stamp, clipboard
export function held(kind, hx, hy) {
  const d = (i, j, c) => px(hx + i, hy + j, C(c));
  if (kind === 'book') { for (let j = -2; j <= 1; j++) for (let i = -1; i <= 2; i++) d(i, j, i === -1 ? 'rd0' : 'rd1'); d(0, -2, 'pp2'); d(1, -2, 'pp2'); }
  else if (kind === 'loupe') { d(0, -2, 'm3'); d(1, -3, 'm3'); d(2, -2, 'm3'); d(1, -1, 'm3'); d(1, -2, 'gl1'); d(0, 0, 'wd1'); }
  else if (kind === 'cards') { for (let j = -2; j <= 0; j++) for (let i = 0; i <= 2; i++) d(i, j, j === -2 ? 'pp2' : 'pp1'); d(0, 0, 'pp0'); }
  else if (kind === 'mug') { d(0, -1, 'pp2'); d(1, -1, 'pp2'); d(0, 0, 'pp1'); d(1, 0, 'pp1'); d(2, -1, 'pp1'); }
  else if (kind === 'stamp') { d(0, -3, 'wd2'); d(0, -2, 'wd1'); d(-1, -1, 'm1'); d(0, -1, 'm1'); d(1, -1, 'm1'); d(-1, 0, 'rd1'); d(0, 0, 'rd1'); d(1, 0, 'rd1'); }
  else if (kind === 'clip') { for (let j = -3; j <= 0; j++) for (let i = 0; i <= 2; i++) d(i, j, 'pp1'); d(1, -4, 'm2'); d(0, -3, 'wd1'); }
  else if (kind === 'chalk') { d(0, 0, 'ch2'); }
}

// the cast: coat colour, skin, hair and the one thing that tells each apart
export const CAST = {
  vig1: { coat: 'c-vig', skin: 2, hair: 'hr1', style: 'beanie', gear: 'beanie', extra: 'rd1' },
  vig2: { coat: 'c-vig', skin: 4, hair: 'hr1', style: 'short', gear: 'beanie', extra: 'g0' },
  lec: { coat: 'c-lec', skin: 1, hair: 'hr2', style: 'bun', held: 'loupe' },
  tia: { coat: 'c-ia', skin: 3, hair: 'hr1', style: 'short', held: 'clip' },
  tibc: { coat: 'c-ibc', skin: 1, hair: 'hr5', style: 'long', gear: 'beret', extra: 'rd0' },
  tii: { coat: 'c-ii', skin: 2, hair: 'hr3', style: 'short', gear: 'scarf', extra: 'g1' },
  ein: { coat: 'c-ins', skin: 4, hair: 'hr1', style: 'short', gear: 'lamp' },
  efi: { coat: 'c-fis', skin: 2, hair: 'hr2', style: 'long', held: 'book' },
  eme: { coat: 'c-mem', skin: 1, hair: 'hr4', style: 'bun', held: 'cards' },
  muse: { coat: 'c-muse', skin: 3, hair: 'hr1', style: 'long', gear: 'phones' },
  dir: { coat: 'c-dir', skin: 2, hair: 'hr1', style: 'short', gear: 'headset' },
  sen: { coat: 'c-sen', skin: 1, hair: 'hr4', style: 'bald', held: 'mug', gear: 'glasses' },
  pro: { coat: 'c-pro', skin: 3, hair: 'hr2', style: 'short', held: 'stamp' },
  lv: { coat: 'c-lv', skin: 1, hair: 'hr4', style: 'short', gear: 'tophat' },
};
