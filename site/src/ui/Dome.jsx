import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { WORDS, format } from '../words.js';
import { H, W, bind, palette } from './dome/engine.js';
import { SIDE, TAGS, TWO, frame, slip } from './dome/scene.js';
import { moment, plan } from './dome/script.js';
import { useWidth } from './width.js';
import './dome/dome.css';

const FPS = 12;
const TALLEST = 560;
// the screens' axes when a beat brings no light curve
const BLANK = { x0: 0, x1: 1, f0: 1, f1: 10 };

// the scale in half steps, so a retina screen gets whole device pixels; below the scene's width it pans at one pixel
const fit = (width) => [1.5, 2, 2.5, 3].reduce((s, k) => (W * k <= width && H * k <= TALLEST ? k : s), 1);

// pixels of an image, read once it has loaded
function useImage(src, read) {
  const [out, setOut] = useState(null);
  useEffect(() => {
    if (!src) return undefined;
    let live = true;
    const im = new Image();
    im.onload = () => {
      const c = document.createElement('canvas');
      c.width = im.naturalWidth;
      c.height = im.naturalHeight;
      const ctx = c.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(im, 0, 0);
      if (live) setOut(read(ctx));
    };
    im.src = src;
    return () => { live = false; };
  }, [src]);
  return out;
}

// the sky through the slit: the field around the object in 4×4 blocks, averaged, colours untouched
function slit(ctx, at) {
  const [cx, cy] = at;
  const cols = 34, rows = 52, k = 4;
  const x0 = Math.round(cx - (cols / 2) * k), y0 = Math.round(cy - 20 * k);
  const d = ctx.getImageData(x0, y0, cols * k, rows * k).data;
  return Array.from({ length: rows }, (_, j) => Array.from({ length: cols }, (__, i) => [0, 1, 2].map((c) => {
    let s = 0;
    for (let v = 0; v < k; v++) for (let u = 0; u < k; u++) s += d[((j * k + v) * cols * k + i * k + u) * 4 + c];
    return Math.round(s / (k * k));
  })));
}

// the first three cutouts at their native pixels, the 17 around the centre, never resampled
function plates(ctx, { tile, gap, pixel }) {
  const n = Math.round(tile / pixel), c = Math.floor(n / 2);
  return [0, 1, 2].map((t) => Array.from({ length: 17 }, (_, j) => Array.from({ length: 17 }, (__, i) => {
    const d = ctx.getImageData(t * (tile + gap) + (c - 8 + i) * pixel, (c - 8 + j) * pixel, 1, 1).data;
    return [d[0], d[1], d[2]];
  })));
}

// a call's short line, in the site's words
function line(c, w, f) {
  const d = c.decision || '';
  const hyp = (h) => w.hyp[h] || h;
  if (c.role === 'reader') {
    const m = /^(real|bogus) \(([\d.]+)\)$/.exec(d);
    return m ? w.reads(m[1] === 'real', f.pct(Number(m[2]))) : '';
  }
  if (c.role === 'theorist') return w.defends(hyp(d.replace('defends ', '')));
  if (c.role === 'skeptic' && c.lens === 'instrument') return d === 'artifact' ? w.artifact : w.realSource;
  if (c.role === 'skeptic' && c.lens === 'physics') return d.startsWith('doubts ') ? w.doubts(d.slice(7).split(', ').map(hyp)) : w.noObjection;
  if (c.role === 'skeptic') return d === 'recognises it' ? w.recognises : w.forgets;
  if (c.role === 'llm_only') return w.alone(Number((/\d+/.exec(d) || ['0'])[0]));
  if (c.role === 'director' || c.role === 'senior') return w.directs(d.split(' ')[0]);
  if (c.role === 'forecaster') return w.words;
  if (c.role === 'leverrier' && d.startsWith('proposes ')) return w.proposes(f.name(d.slice(9)));
  return '';
}

// each bubble opens to its own side; if it would cover another or leave the view it tries the other side, then rises
function place(els, want, s, view) {
  const boxes = [];
  const order = want.slice().sort((a, b) => (a.think ? 0 : 1) - (b.think ? 0 : 1));
  for (const b of order) {
    const el = els.get(b.id);
    if (!el) continue;
    const w = el.offsetWidth, h = el.offsetHeight, x = b.x * s, y = b.y * s;
    const pref = SIDE[b.id] || 'c';
    const sides = [pref, pref === 'l' ? 'r' : 'l', 'c'];
    const at = (side) => (side === 'l' ? x - w + 14 : side === 'r' ? x - 14 : x - w / 2);
    let pick = null;
    for (let lift = 0; lift <= 3 && !pick; lift++) {
      for (const side of sides) {
        const x0 = at(side), y0 = y - h - 6 - lift * (h + 6);
        const inside = x0 >= view[0] + 2 && x0 + w <= view[1] - 2 && y0 >= 2;
        const clear = boxes.every((o) => x0 + w + 4 <= o.x0 || o.x0 + o.w + 4 <= x0 || y0 + h + 10 <= o.y0 || o.y0 + o.h + 10 <= y0);
        if (inside && clear) { pick = { x0, y0, lift }; break; }
      }
    }
    if (!pick) pick = { x0: Math.min(Math.max(at(pref), view[0] + 2), view[1] - w - 2), y0: y - h - 6, lift: 0 };
    el.style.left = `${Math.round(pick.x0)}px`;
    el.style.top = `${Math.round(pick.y0)}px`;
    el.style.setProperty('--tx', `${Math.round(Math.min(Math.max(x - pick.x0, 8), w - 8))}px`);
    el.style.setProperty('--ty', `${Math.round(y - pick.y0 - h)}px`);
    // a lifted bubble keeps a dotted thread down to whoever speaks
    if (pick.lift) el.dataset.far = ''; else delete el.dataset.far;
    boxes.push({ x0: pick.x0, y0: pick.y0, w, h });
  }
}

// a name that would sit under a bubble or under another name gives way, the busiest agents' names first
function declutter(over) {
  const boxes = [...over.querySelectorAll('.bub')].map((b) => b.getBoundingClientRect());
  const tags = [...over.querySelectorAll('.tag')].sort((a, b) => a.dataset.rank - b.dataset.rank);
  for (const el of tags) {
    el.style.visibility = '';
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    const hit = boxes.some((o) => r.left < o.right + 2 && o.left < r.right + 2 && r.top < o.bottom && o.top < r.bottom);
    if (hit && el.dataset.rank !== '0') el.style.visibility = 'hidden';
    else boxes.push(r);
  }
}

// the observatory with the team at work: each beat's calls think for their real seconds, then speak to whom they address
export default function Dome({ lang, beats, at, sky, stamps }) {
  const w = WORDS[lang].dome;
  const f = format(lang);
  const [root, width] = useWidth();
  const canvas = useRef(null);
  const over = useRef(null);
  const bubbles = useRef(new Map());
  const clock = useRef({ at: null, start: 0 });
  const aim = useRef(null);
  const [view, setView] = useState(null);
  const field = useImage(sky && sky.src, (ctx) => slit(ctx, sky.at));
  const cuts = useImage(stamps && stamps.src, (ctx) => plates(ctx, stamps));
  const steps = useMemo(() => plan(beats, (c) => line(c, w, f)), [beats, lang]);
  const narrow = width > 0 && width < W;
  const s = narrow ? 1 : fit(width);
  const inset = Math.max(0, Math.floor((width - W * s) / 2));

  useLayoutEffect(() => {
    if (clock.current.at !== at) clock.current = { at, start: performance.now() };
  }, [at]);

  useEffect(() => {
    const el = root.current;
    const p = steps[Math.min(at, steps.length - 1)];
    if (!el || !p) return undefined;
    const ctx = canvas.current.getContext('2d');
    const data = ctx.createImageData(W, H);
    const buf = new Uint32Array(data.data.buffer);
    const pal = palette(el);
    const scene = { pts: [], voices: [], weights: {}, range: BLANK, ...beats[at].scene };
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const draw = (t) => {
      const st = { ...scene, ...moment(p, t), sky: field, stamps: cuts || [] };
      bind(buf, pal);
      const heads = frame(t, st);
      ctx.putImageData(data, 0, 0);
      setView(overlay(st, heads, t, calm));
    };
    let raf = 0;
    let shown = -1;
    let seen = true;
    const tick = (ms) => {
      raf = 0;
      const t = Math.min((ms - clock.current.start) / 1000, p.length);
      if (Math.floor(t * FPS) !== shown || t >= p.length) { shown = Math.floor(t * FPS); draw(t); }
      // the loop stops at the end of the beat and while the scene is off screen
      if (t < p.length && seen) raf = requestAnimationFrame(tick);
    };
    if (calm) draw(Number.isFinite(p.length) ? p.length : 0);
    else raf = requestAnimationFrame(tick);
    const watch = new IntersectionObserver(([e]) => {
      seen = e.isIntersecting;
      if (seen && !raf && !calm) raf = requestAnimationFrame(tick);
    });
    watch.observe(el);
    return () => { cancelAnimationFrame(raf); watch.disconnect(); };
  }, [steps, at, field, cuts]);

  // the names, the bubbles and the sealed slip, in logical pixels
  function overlay(st, heads, t, calm) {
    const tags = Object.entries(TAGS).map(([id, [dx, dy]]) => {
      const h = id === 'vig' ? { x: (heads.vig[0].x + heads.vig[1].x) / 2, y: heads.vig[0].y } : heads[id];
      const seat = st.seats[id];
      const name = seat ? w.theorist(seat === 'adopted' ? seat : w.hyp[seat] || seat) : w.names[id];
      const a = st.agents[id];
      return { id, x: h.x + dx, y: h.y + dy, two: TWO.has(id), rank: a ? (a.talk ? 0 : 1) : 2, name };
    });
    const want = Object.entries(st.agents).filter(([id]) => heads[id]).map(([id, a]) => {
      const h = heads[id];
      const x = h.bx ?? h.x, y = h.by ?? h.top - 3;
      return a.think ? { id, think: true, x, y, secs: Math.floor(a.real), on: calm ? 2 : Math.floor(t / 0.3) % 3 } : { id, x, y, text: a.text };
    }).filter((b) => b.think || b.text);
    const sp = slip();
    const paper = st.sealed !== null && st.sealed !== undefined && st.slip >= 1 ? { x: sp[0] - 11, y: sp[1] - 10, text: f.pct(st.sealed) } : null;
    const talk = Object.entries(st.agents).filter(([, a]) => a.talk);
    const ids = talk.length ? talk.flatMap(([id, a]) => [id, ...a.to]) : Object.keys(st.agents);
    const xs = ids.map((id) => heads[id]).filter(Boolean).map((h) => h.x);
    return { tags, want, paper, focus: xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null };
  }

  useLayoutEffect(() => {
    const el = root.current;
    if (!view || !el) return;
    // bubbles may open over the night on either side of the scene
    const left = narrow ? -el.scrollLeft : inset;
    place(bubbles.current, view.want, s, [-left, el.clientWidth - left]);
    declutter(over.current);
  }, [view, s, narrow, inset]);

  // on a phone the strip pans to whoever is acting
  useEffect(() => {
    const el = root.current;
    if (!narrow || !view || view.focus === null) return;
    const x = Math.round(Math.min(W - el.clientWidth, Math.max(0, view.focus - el.clientWidth / 2)));
    if (aim.current !== null && Math.abs(x - aim.current) <= 40) return;
    const first = aim.current === null;
    aim.current = x;
    el.scrollTo({ left: x, behavior: first || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }, [view && view.focus, narrow]);

  const size = { width: W * s, height: H * s };
  return (
    <div className={`dome${narrow ? ' narrow' : ''}${s < 1.5 ? ' compact' : ''}`} ref={root} role="img" aria-label={w.label} style={{ height: H * s + 2 }}>
      <div className="stage" style={{ ...size, left: inset }}>
        <canvas ref={canvas} width={W} height={H} style={size} />
        {view && (
          <div className="over" ref={over} style={size} aria-hidden="true">
            {view.tags.map((g) => (
              <span key={g.id} className={`tag${g.two ? ' two' : ''}${g.rank > 1 ? ' idle' : ''}`} data-rank={g.rank} style={{ left: g.x * s, top: g.y * s }}>{g.name}</span>
            ))}
            {view.paper && <span className="slip" style={{ left: view.paper.x * s, top: view.paper.y * s, width: 22 * s, height: 10 * s }}>{view.paper.text}</span>}
            {view.want.map((b) => (
              <div key={b.id + (b.think ? 't' : 's')} ref={(el) => (el ? bubbles.current.set(b.id, el) : bubbles.current.delete(b.id))} className={`bub${b.think ? ' think' : ''}`}>
                {b.think ? <><span className="dots">{[0, 1, 2].map((i) => <i key={i} className={i === b.on ? 'on' : undefined} />)}</span><span>{w.seconds(b.secs)}</span></> : b.text}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
