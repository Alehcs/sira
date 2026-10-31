import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { WORDS, format } from '../words.js';
import { useWidth } from './width.js';

const f1 = (v) => v.toFixed(1);
const minus = (v) => String(v).replace('-', '−');
const STEPS = [1, 2, 5, 10, 20, 50, 100, 200];
const MINOR = { 1: 0, 2: 1, 5: 1, 10: 2, 20: 5, 50: 10, 100: 20, 200: 50 };
const SPAN = 2; // the narrowest zoom, in days
const magOf = (v) => 23.9 - 2.5 * Math.log10(v);
const fluxOf = (m) => 10 ** ((23.9 - m) / 2.5);
const none = (v) => v === undefined || v === null || v === false;

// the width of a label in the figure's sans type, for placing it
function textWidth(text) {
  const c = textWidth.ctx || (textWidth.ctx = document.createElement('canvas').getContext('2d'));
  c.font = "13px 'IBM Plex Sans', sans-serif";
  return c.measureText(text).width + 2;
}

// a round flux at or beyond v, for the ends of the log axis
function nice(v, up) {
  const e = 10 ** Math.floor(Math.log10(v));
  const steps = [1, 2, 3, 5, 10];
  return e * (up ? steps.find((s) => s * e >= v) : steps.slice().reverse().find((s) => s * e <= v));
}

// a time window kept inside the whole range and no narrower than SPAN, or null for the whole range
function fit([a, b], [A, B]) {
  if (b - a >= B - A - 1e-6) return null;
  if (b - a < SPAN) { const c = (a + b) / 2; a = c - SPAN / 2; b = c + SPAN / 2; }
  if (a < A) { b += A - a; a = A; }
  if (b > B) { a -= b - B; b = B; }
  return [Math.max(a, A), Math.min(b, B)];
}

// one measurement in words, for its tooltip
function describe(p, start, w, f) {
  const when = start ? f.stamp(new Date(new Date(start).getTime() + p.day * 86400000).toISOString()) : w.day(f.num(p.day, 2));
  const band = p.band === 'g' ? 'g' : 'r';
  if (p.limit) return { when, band, lines: [w.below(`${f.num(p.flux, 1)} µJy`, f.num(magOf(p.flux), 2))] };
  const pm = (v, d) => (p.err ? ` ± ${f.num(v, d)}` : '');
  return { when, band, lines: [`${f.num(p.flux, 1)}${pm(p.err, 1)} µJy`, `${f.num(magOf(p.flux), 2)}${pm((1.0857 * p.err) / p.flux, 2)} mag AB`] };
}

function Mark({ k }) {
  if (k === 'g') return <svg width="12" height="12" aria-hidden="true"><circle className="ptg" cx="6" cy="6" r="3.6" /></svg>;
  if (k === 'r') return <svg width="12" height="12" aria-hidden="true"><rect className="ptr" x="2.6" y="2.6" width="6.8" height="6.8" /></svg>;
  if (k === 'lim') return <svg width="28" height="12" aria-hidden="true"><path className="lim sg" d="M2.5 2.5h9l-4.5 8z" /><path className="lim sr" d="M16.5 2.5h9l-4.5 8z" /></svg>;
  return <svg width="24" height="12" aria-hidden="true"><rect className="fill" x="1" y="2" width="22" height="8" /><path className="med" d="M1 6H23" /></svg>;
}

// the light curve: points {day, band, flux, err, limit}, forecasts {band, rows: [[day, mean, sd]], style, label, hash, place, z}
// axes {x, y, mag} titles the axes in words, mags={false} drops the magnitude scale, bandNames {g, r} names the bands in words,
// legend {g, r, lim, fc} renames the switches under it and keys adds marks it only explains, as [{mark, text}]
export default function Figure({ lang, start, points = [], forecasts = [], rings = [], note, now, nowLabel, reference, target, x, y, label, axes, mags = true, bandNames, legend = {}, keys = [] }) {
  const [ref, W] = useWidth();
  const id = useId().replace(/:/g, '');
  const clip = `plot${id}`;
  const [view, setView] = useState(null);
  const [hidden, setHidden] = useState({});
  const [mode, setMode] = useState('flux');
  const [pick, setPick] = useState(null);
  const [box, setBox] = useState(null);
  const svg = useRef(null);
  const plot = useRef(null);
  const geo = useRef(null);
  const drag = useRef({ ptrs: new Map() });
  const tipBox = useRef(null);
  const anchor = useRef(null);
  const w = WORDS[lang].fig;
  const f = format(lang);
  const narrow = W < 500;
  const H = narrow ? 300 : Math.round(Math.max(300, Math.min(440, W * 0.64)));

  // the wheel zooms once the reader is in the chart, or with ctrl as trackpads pinch
  useEffect(() => {
    const el = svg.current;
    if (!el) return undefined;
    const wheel = (e) => {
      const g = geo.current;
      const r = el.getBoundingClientRect();
      const px = e.clientX - r.left;
      if (!g || px < g.L || px > g.R || !(e.ctrlKey || e.metaKey || document.activeElement === plot.current)) return;
      e.preventDefault();
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        const k = (g.x1 - g.x0) / (g.R - g.L);
        setView(fit([g.x0 + e.deltaX * k, g.x1 + e.deltaX * k], g.base));
        return;
      }
      const day = g.inv(px);
      const s = Math.exp(Math.max(-0.5, Math.min(0.5, e.deltaY * (e.ctrlKey ? 0.01 : 0.002))));
      setView(fit([day - (day - g.x0) * s, day + (g.x1 - day) * s], g.base));
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  }, [W > 0]);

  // the tooltip beside its point, kept inside the figure
  useLayoutEffect(() => {
    const el = tipBox.current;
    const a = anchor.current;
    if (!el || !a) return;
    const tw = el.offsetWidth;
    const th = el.offsetHeight;
    const left = a.x > a.w / 2 ? a.x - 14 - tw : a.x + 14;
    const top = a.y > a.h / 2 ? a.y - 14 - th : a.y + 14;
    el.style.left = `${Math.max(2, Math.min(a.w - tw - 2, left))}px`;
    el.style.top = `${Math.max(2, Math.min(a.h - th - 2, top))}px`;
  });

  if (!W) return <div className="figure" ref={ref} style={{ height: H }} />;

  const m = narrow ? { l: 38, r: 38, t: 26, b: start ? 48 : 32 } : { l: 54, r: 48, t: 28, b: start ? 52 : 36 };
  if (!mags) m.r = narrow ? 14 : 20;
  if (axes) { m.b += 22; m.t += 6; }
  const L = m.l;
  const T = m.t;
  const R = W - m.r;
  const B = H - m.b;
  const days = points.map((p) => p.day).concat(forecasts.flatMap((fc) => fc.rows.map((r) => r[0])), now ?? [], target ? target.day : []);
  const fluxes = points.map((p) => p.flux).concat(forecasts.flatMap((fc) => fc.rows.map((r) => r[1])), reference ? reference.flux : []).filter((v) => v > 0);
  const base = x ? [...x] : [Math.floor(Math.min(...days)) - 1, Math.ceil(Math.max(...days)) + 1];
  if (axes && target && target.label) {
    // in words, the answer's day keeps room on its right for its own label
    const room = R - L - 10 - textWidth(target.label);
    if (room > 0 && target.day > base[0]) base[1] = Math.max(base[1], Math.ceil(base[0] + ((target.day - base[0]) * (R - L)) / room));
  }
  const zoomed = view !== null;
  const [x0, x1] = view || base;
  const [lo, hi] = y || [nice(Math.min(...fluxes) / 1.3, false), nice(Math.max(...fluxes) * 1.3, true)];
  const X = (d) => L + ((d - x0) / (x1 - x0)) * (R - L);
  const Y = (v) => T + (1 - (Math.log10(Math.max(v, lo / 100)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (B - T);
  const dateOf = (d) => new Date(new Date(start).getTime() + d * 86400000).toISOString();
  const inside = (d) => !zoomed || (d >= x0 && d <= x1);
  const mag = mode === 'mag';
  const bandOf = (b) => (b === 'g' ? 'g' : 'r');
  const shown = points.map((p, i) => ({ ...p, i })).filter((p) => !hidden[bandOf(p.band)] && !(p.limit && hidden.lim));
  const fcs = hidden.fc ? [] : forecasts.filter((fc) => !hidden[bandOf(fc.band)]);
  const nowAt = !none(now) && inside(now) ? now : null;
  const goal = target && inside(target.day) ? target : null;
  const nowText = nowLabel || w.now;
  const nowWidth = Math.max(46, nowText.length * 7.3);
  const out = [];
  const ticks = [];

  const bright = 23.9 - 2.5 * Math.log10(hi);
  const faint = 23.9 - 2.5 * Math.log10(lo);
  const every = faint - bright > 9 ? 2 : 1;
  if (!mag) {
    // inward ticks on all four sides, minor ones on the log axis
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e += 1) {
      for (let n = 1; n < 10; n += 1) {
        const v = n * 10 ** e;
        if (v < lo * 0.999 || v > hi * 1.001) continue;
        const major = n === 1 || n === 3;
        const len = major ? 7 : 3.5;
        ticks.push(`M${L} ${f1(Y(v))}h${len}M${R} ${f1(Y(v))}h-${len}`);
        if (major) out.push(<text key={`f${v}`} x={L - 8} y={f1(Y(v) + 4)} textAnchor="end">{v >= 1 ? Math.round(v) : f.num(v, 1)}</text>);
      }
    }
    for (let q = Math.ceil(bright); mags && q <= faint; q += 1) {
      if (q % every) continue;
      const at = Y(fluxOf(q));
      ticks.push(`M${R} ${f1(at)}h-5`);
      out.push(<text key={`m${q}`} x={R + 8} y={f1(at + 4)}>{q}</text>);
    }
  } else {
    // magnitudes on the left, the smaller number higher up, and µJy on the right
    const minor = every === 2 ? 1 : 0.5;
    for (let q = Math.ceil(bright / minor) * minor; q <= faint; q += minor) {
      const major = Number.isInteger(q) && q % every === 0;
      const at = Y(fluxOf(q));
      const len = major ? 7 : 3.5;
      ticks.push(`M${L} ${f1(at)}h${len}M${R} ${f1(at)}h-${len}`);
      if (major) out.push(<text key={`m${q}`} x={L - 8} y={f1(at + 4)} textAnchor="end">{q}</text>);
    }
    for (let e = Math.floor(Math.log10(lo)); mags && e <= Math.ceil(Math.log10(hi)); e += 1) {
      for (const n of [1, 3]) {
        const v = n * 10 ** e;
        if (v < lo * 0.999 || v > hi * 1.001) continue;
        ticks.push(`M${R} ${f1(Y(v))}h-5`);
        out.push(<text key={`f${v}`} x={R + 8} y={f1(Y(v) + 4)}>{v >= 1 ? Math.round(v) : f.num(v, 1)}</text>);
      }
    }
  }
  const step = STEPS.find((s) => s * ((R - L) / (x1 - x0)) >= (narrow ? 56 : 60)) || 200;
  const small = MINOR[step] || step;
  for (let d = Math.ceil(x0 / small) * small; d <= x1; d += small) {
    const major = d % step === 0;
    const len = major ? 7 : 3.5;
    ticks.push(`M${f1(X(d))} ${B}v-${len}M${f1(X(d))} ${T}v${len}`);
    if (!major || (zoomed && (X(d) < (start ? 24 : 10) || X(d) > W - (start ? 24 : 10)))) continue;
    out.push(<text key={`d${d}`} x={f1(X(d))} y={B + 18} textAnchor="middle">{minus(d)}</text>);
    if (start) out.push(<text key={`c${d}`} x={f1(X(d))} y={B + 35} textAnchor="middle">{f.short(dateOf(d))}</text>);
  }
  out.push(<path key="ticks" className="tick" d={ticks.join('')} />);
  if (axes) {
    out.push(<text key="ujy" className="axis" x={2} y={T - 12}>{mag ? axes.mag || axes.y : axes.y}</text>);
    out.push(<text key="days" className="axis" x={f1((L + R) / 2)} y={H - 6} textAnchor="middle">{axes.x}</text>);
  } else {
    if (mag) out.push(<text key="ujy" x={2} y={T - 11}>{w.magTitle}</text>);
    else out.push(<text key="ujy" x={L - 8} y={T - 11} textAnchor="end">µJy</text>);
    out.push(<text key="days" x={R + 8} y={B + 18}>{w.days}</text>);
  }
  if (mags) out.push(<text key="ab" x={W - 2} y={T - 11} textAnchor="end">{mag ? 'µJy' : 'mag AB'}</text>);

  // forecasts: mean ± z sigma, clipped to the frame, each named at its end with its seal
  const bands = [];
  const names = [];
  fcs.forEach((fc, i) => {
    const z = fc.z ?? 1.645;
    const s = fc.band === 'g' ? 'sg' : 'sr';
    const up = fc.rows.map(([d, mu, sd]) => `${f1(X(d))},${f1(Y(mu + z * sd))}`);
    const dn = fc.rows.slice().reverse().map(([d, mu, sd]) => `${f1(X(d))},${f1(Y(mu - z * sd))}`);
    if (fc.style === 'sealed' || !fc.style) {
      bands.push(<polygon key={`a${i}`} className="fill" points={up.concat(dn).join(' ')} />);
      bands.push(<polyline key={`u${i}`} className={`edge ${s}`} points={up.join(' ')} />);
      bands.push(<polyline key={`l${i}`} className={`edge ${s}`} points={dn.join(' ')} />);
      bands.push(<polyline key={`m${i}`} className={`med ${s}`} points={fc.rows.map(([d, mu]) => `${f1(X(d))},${f1(Y(mu))}`).join(' ')} />);
    } else {
      bands.push(<polyline key={`u${i}`} className={`${fc.style} ${s}`} points={up.join(' ')} />);
      bands.push(<polyline key={`l${i}`} className={`${fc.style} ${s}`} points={dn.join(' ')} />);
    }
    if (!fc.label) return;
    const end = fc.rows[fc.rows.length - 1];
    if (zoomed && (end[0] < x0 || fc.rows[0][0] > x1)) return;
    const lower = fc.place === 'lower';
    const edge = (r) => (lower ? r[1] - z * r[2] : r[1] + z * r[2]);
    const hash = narrow ? '' : fc.hash || '';
    const tw = Math.max(fc.label.length * 7.4, hash ? 60 : 0);
    let tx = X(end[0]) + 7;
    let ty;
    if (tx + tw <= R - 4) {
      ty = lower ? Y(Math.max(edge(end), lo * 1.05)) + 14 : Y(Math.min(edge(end), hi * 0.97)) - 6;
    } else {
      // too close to the frame: above or below the band instead
      tx = R - 4 - tw;
      const near = fc.rows.filter((r) => X(r[0]) >= tx - 8).map(edge);
      const vals = near.length ? near : [edge(end)];
      ty = lower ? Y(Math.max(Math.min(...vals), lo * 1.05)) + 14 : Y(Math.min(Math.max(...vals), hi * 0.97)) - 7 - (hash ? 15 : 0);
    }
    ty = Math.min(Math.max(ty, T + 14), B - (hash ? 21 : 6));
    names.push(<text key={`n${i}`} className="hyp" x={f1(tx)} y={f1(ty)}>{fc.label}</text>);
    if (hash) names.push(<text key={`h${i}`} x={f1(tx)} y={f1(ty + 15)}>{hash}</text>);
  });
  out.push(<g key="bands" clipPath={`url(#${clip})`}>{bands}</g>);
  out.push(...names);

  if (reference) {
    out.push(<line key="ref" className="ref" x1={L} x2={R} y1={f1(Y(reference.flux))} y2={f1(Y(reference.flux))} />);
    if (reference.label && !axes) out.push(<text key="refl" className="refl" x={L + 8} y={f1(Y(reference.flux) - 6)}>{reference.label}</text>);
  }
  if (goal) {
    out.push(<line key="target" className="target" x1={f1(X(goal.day))} x2={f1(X(goal.day))} y1={T} y2={B} />);
    // the label sits beside its line, never across it, nor across the line of now in words
    const right = X(goal.day) + 6 + (axes ? textWidth(goal.label || '') : String(goal.label || '').length * 8) <= R - 4;
    const edge = axes && !right && nowAt !== null && nowAt < goal.day ? Math.min(X(nowAt), X(goal.day)) : X(goal.day);
    if (goal.label) out.push(<text key="targetl" className={`refl${axes ? ' plain halo' : ''}`} x={f1(right ? X(goal.day) + 6 : edge - 6)} y={T + 16} textAnchor={right ? 'start' : 'end'}>{goal.label}</text>);
  }

  // the measurements: one sigma bars, g circles, r squares, open triangles for upper limits
  const err = { g: [], r: [] };
  const lim = { g: [], r: [] };
  const dot = { g: [], r: [] };
  for (const p of shown) {
    const b = p.band === 'g' ? 'g' : 'r';
    const px = X(p.day);
    const py = Y(p.flux);
    if (p.limit) {
      lim[b].push(`M${f1(px - 4.5)} ${f1(py - 3.5)}h9l-4.5 8z`);
      continue;
    }
    if (p.err && mag) {
      // in magnitudes the bar is the same size above and below
      const s = (1.0857 * p.err) / p.flux;
      err[b].push(`M${f1(px)} ${f1(Y(fluxOf(magOf(p.flux) - s)))}V${f1(Y(fluxOf(magOf(p.flux) + s)))}`);
    } else if (p.err) err[b].push(`M${f1(px)} ${f1(Y(p.flux + p.err))}V${f1(Y(p.flux - p.err))}`);
    dot[b].push(b === 'g' ? `M${f1(px - 3.6)} ${f1(py)}a3.6 3.6 0 1 0 7.2 0a3.6 3.6 0 1 0 -7.2 0z` : `M${f1(px - 3.4)} ${f1(py - 3.4)}h6.8v6.8h-6.8z`);
  }
  out.push(
    <g key="points" clipPath={`url(#${clip})`}>
      <path className="err sg" d={err.g.join('')} /><path className="err sr" d={err.r.join('')} />
      <path className="lim sg" d={lim.g.join('')} /><path className="lim sr" d={lim.r.join('')} />
      <path className="ptg" d={dot.g.join('')} /><path className="ptr" d={dot.r.join('')} />
    </g>,
  );
  const ringsIn = rings.filter((r) => inside(r.day));
  for (const r of ringsIn) out.push(<circle key={`r${r.day}`} className="ring" cx={f1(X(r.day))} cy={f1(Y(r.flux))} r="8.5" />);
  if (note && ringsIn.length) {
    const nx = X(Math.min(...ringsIn.map((r) => r.day))) - 7;
    const ny = Y(Math.max(...ringsIn.map((r) => r.flux))) - (narrow ? 38 : 22);
    out.push(<text key="note" className="warn" x={f1(nx)} y={f1(ny)} textAnchor="end">{note.text}</text>);
    if (note.sub && !narrow) out.push(<text key="notes" x={f1(nx)} y={f1(ny + 16)} textAnchor="end">{note.sub}</text>);
  }

  // each band named once, at its first detection
  for (const b of bandNames ? [] : ['r', 'g']) {
    const p = shown.find((q) => q.band === b && !q.limit && (!zoomed || (X(q.day) - 20 > L && q.day <= x1)));
    if (p) out.push(<text key={`b${b}`} className={`band-${b}`} x={f1(X(p.day) - 9)} y={f1(Y(p.flux) + 5)} textAnchor="end">{b}</text>);
  }

  // in words, the line to beat and the bands go wherever they cover the fewest marks, over the points
  if (axes) {
    const marks = shown.map((p) => [X(p.day), Y(p.flux)]);
    const walls = [nowAt, goal && goal.day].filter((d) => !none(d)).map(X);
    const taken = [];
    if (goal && goal.label) {
      const tw = textWidth(goal.label);
      const right = X(goal.day) + 6 + tw <= R - 4;
      const edge = !right && nowAt !== null && nowAt < goal.day ? Math.min(X(nowAt), X(goal.day)) : X(goal.day);
      taken.push(right ? { x0: X(goal.day), x1: X(goal.day) + 8 + tw, y0: T, y1: T + 22 } : { x0: edge - 8 - tw, x1: edge, y0: T, y1: T + 22 });
    }
    if (nowAt !== null) taken.push({ x0: X(nowAt) - nowWidth - 14, x1: X(nowAt) + nowWidth + 14, y0: B - (start ? 38 : 22), y1: B });
    const cost = (b) => {
      if (b.x0 < L + 2 || b.x1 > R - 2 || b.y0 < T + 2 || b.y1 > B - 2) return Infinity;
      let n = 0;
      for (const [px, py] of marks) if (px > b.x0 - 6 && px < b.x1 + 6 && py > b.y0 - 6 && py < b.y1 + 6) n += 1;
      for (const t of taken) if (b.x0 < t.x1 && b.x1 > t.x0 && b.y0 < t.y1 && b.y1 > t.y0) n += 100;
      for (const v of walls) if (b.x0 < v && b.x1 > v) n += 50;
      return n;
    };
    const place = (options) => {
      let best = null;
      for (const o of options) {
        const bx = o.anchor === 'end' ? { x0: o.x - o.w, x1: o.x, y0: o.y - 12, y1: o.y + 4 } : { x0: o.x, x1: o.x + o.w, y0: o.y - 12, y1: o.y + 4 };
        const c = cost(bx);
        if (!best || c < best.c) best = { ...o, box: bx, c };
      }
      if (best && best.c < Infinity) { taken.push(best.box); return best; }
      return null;
    };
    if (reference && reference.label) {
      const w0 = textWidth(reference.label);
      const ry = Y(reference.flux);
      const xs = [];
      for (let at = L + 8; at + w0 <= R - 8; at += 24) xs.push(at);
      const at = place([-6, 16].flatMap((dy) => xs.map((v) => ({ x: v, anchor: 'start', y: ry + dy, w: w0 }))));
      if (at) out.push(<text key="refl" className="refl plain halo" x={f1(at.x)} y={f1(at.y)} textAnchor={at.anchor}>{reference.label}</text>);
    }
    for (const b of ['r', 'g']) {
      const text = bandNames ? bandNames[b] : b;
      const w0 = textWidth(text);
      const options = shown.filter((p) => p.band === b && !p.limit).flatMap((p) => {
        const px = X(p.day);
        const py = Y(p.flux);
        return [[px - 9, 'end', py + 5], [px + 9, 'start', py + 5], [px - 6, 'end', py - 10], [px + 6, 'start', py - 10],
          [px - 6, 'end', py + 20], [px + 6, 'start', py + 20]].map(([v, anchor, h]) => ({ x: v, anchor, y: h, w: w0 }));
      });
      const at = place(options);
      if (at) out.push(<text key={`b${b}`} className={`band-${b} plain halo`} x={f1(at.x)} y={f1(at.y)} textAnchor={at.anchor}>{text}</text>);
    }
  }

  if (nowAt !== null) {
    // in words, the label keeps clear of the answer's day just after it
    const crowded = axes && goal && goal.day > nowAt && X(goal.day) - X(nowAt) < 60;
    const right = X(nowAt) + 7 + nowWidth <= R - 4 && !crowded;
    const at = { x: f1(right ? X(nowAt) + 7 : X(nowAt) - 7), textAnchor: right ? 'start' : 'end' };
    out.push(<line key="now" className="now" x1={f1(X(nowAt))} x2={f1(X(nowAt))} y1={T} y2={B} />);
    out.push(<text key="nowt" {...at} y={start ? B - 24 : B - 9}>{nowText}</text>);
    if (start) out.push(<text key="nowd" className="nowl" {...at} y={B - 9}>{f.short(dateOf(nowAt))}</text>);
  }
  out.push(<rect key="frame" className="frame" x={L + 0.5} y={T + 0.5} width={R - L - 1} height={B - T - 1} />);

  // what the pointer and the keys can reach: the shown points inside the frame, in time order
  const marks = shown.filter((p) => inside(p.day)).map((p) => ({ i: p.i, x: X(p.day), y: Y(p.flux) }));
  const order = shown.slice().sort((a, b) => a.day - b.day).map((p) => p.i);
  geo.current = { L, R, T, B, x0, x1, base, zoomed, marks, inv: (px) => x0 + ((px - L) / (R - L)) * (x1 - x0) };
  const picked = pick && points[pick.i] && shown.some((p) => p.i === pick.i) && inside(points[pick.i].day) ? points[pick.i] : null;
  if (picked) out.push(<circle key="pick" className="pick" cx={f1(X(picked.day))} cy={f1(Y(picked.flux))} r="7.5" />);
  if (box) out.push(<rect key="zoombox" className="zoombox" x={f1(box[0])} y={T} width={f1(box[1] - box[0])} height={B - T} />);

  const local = (e) => { const r = svg.current.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const nearest = (p, radius) => {
    let best = null;
    for (const q of geo.current.marks) {
      const d = Math.hypot(q.x - p.x, q.y - p.y);
      if (d <= radius && (!best || d < best.d)) best = { i: q.i, d };
    }
    return best;
  };
  const zoomAt = (day, s) => {
    const g = geo.current;
    setView(fit([day - (day - g.x0) * s, day + (g.x1 - day) * s], g.base));
  };
  const down = (e) => {
    const g = geo.current;
    const p = local(e);
    const d = drag.current;
    d.ptrs.set(e.pointerId, p);
    try { svg.current.setPointerCapture(e.pointerId); } catch (err0) { /* the pointer may be gone */ }
    if (d.ptrs.size === 2) {
      const [a, b] = [...d.ptrs.values()];
      d.pinch = { dist: Math.max(20, Math.abs(a.x - b.x)), day: g.inv((a.x + b.x) / 2), span: g.x1 - g.x0 };
      d.start = null;
      setBox(null);
      return;
    }
    d.start = p.x >= g.L && p.x <= g.R && p.y >= g.T && p.y <= g.B ? { ...p, view: [g.x0, g.x1], pan: g.zoomed && !e.shiftKey, moved: false } : null;
  };
  const move = (e) => {
    const g = geo.current;
    const p = local(e);
    const d = drag.current;
    if (d.ptrs.has(e.pointerId)) d.ptrs.set(e.pointerId, p);
    if (d.pinch && d.ptrs.size === 2) {
      const [a, b] = [...d.ptrs.values()];
      const span = (d.pinch.span * d.pinch.dist) / Math.max(20, Math.abs(a.x - b.x));
      const at = ((a.x + b.x) / 2 - g.L) / (g.R - g.L);
      setView(fit([d.pinch.day - at * span, d.pinch.day + (1 - at) * span], g.base));
      return;
    }
    const s = d.start;
    if (s) {
      const dx = p.x - s.x;
      if (!s.moved && Math.abs(dx) < 5) return;
      s.moved = true;
      setPick(null);
      if (s.pan) {
        const k = (s.view[1] - s.view[0]) / (g.R - g.L);
        setView(fit([s.view[0] - dx * k, s.view[1] - dx * k], g.base));
      } else setBox([Math.max(g.L, Math.min(s.x, p.x)), Math.min(g.R, Math.max(s.x, p.x))]);
      return;
    }
    if (e.pointerType !== 'mouse' || d.ptrs.size) return;
    const inFrame = p.x >= g.L && p.x <= g.R && p.y >= g.T && p.y <= g.B;
    const near = inFrame ? nearest(p, 40) : null;
    if (near && (!pick || pick.i !== near.i)) setPick({ i: near.i, how: 'hover' });
    else if (!near && pick && pick.how === 'hover') setPick(null);
  };
  const up = (e) => {
    const g = geo.current;
    const p = local(e);
    const d = drag.current;
    d.ptrs.delete(e.pointerId);
    if (d.pinch) { if (!d.ptrs.size) d.pinch = null; d.start = null; return; }
    const s = d.start;
    d.start = null;
    if (!s) return;
    if (s.moved && !s.pan) {
      setBox(null);
      const a = Math.max(g.L, Math.min(s.x, p.x));
      const b = Math.min(g.R, Math.max(s.x, p.x));
      if (b - a > 8) setView(fit([g.inv(a), g.inv(b)], g.base));
      return;
    }
    if (!s.moved && e.pointerType !== 'mouse') {
      const near = nearest(p, 44);
      setPick(near ? { i: near.i, how: 'tap' } : null);
    }
  };
  const cancel = (e) => {
    const d = drag.current;
    d.ptrs.delete(e.pointerId);
    if (!d.ptrs.size) d.pinch = null;
    d.start = null;
    setBox(null);
  };
  const key = (e) => {
    const g = geo.current;
    if (['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) {
      if (!order.length) return;
      e.preventDefault();
      const at = picked ? order.indexOf(pick.i) : -1;
      let next;
      if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = order.length - 1;
      else if (at < 0) next = e.key === 'ArrowRight' ? 0 : order.length - 1;
      else next = Math.max(0, Math.min(order.length - 1, at + (e.key === 'ArrowRight' ? 1 : -1)));
      const day = points[order[next]].day;
      if (g.zoomed && (day < g.x0 || day > g.x1)) {
        const half = (g.x1 - g.x0) / 2;
        setView(fit([day - half, day + half], g.base));
      }
      setPick({ i: order[next], how: 'key' });
    } else if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      zoomAt(picked ? picked.day : (g.x0 + g.x1) / 2, 0.6);
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault();
      zoomAt(picked ? picked.day : (g.x0 + g.x1) / 2, 1 / 0.6);
    } else if (e.key === '0') {
      setView(null);
    } else if (e.key === 'Escape' && pick) {
      setPick(null);
    }
  };

  let tip = null;
  if (picked) {
    const t = describe(picked, start, w, f);
    anchor.current = { x: X(picked.day), y: Y(picked.flux), w: W, h: H };
    tip = { t, text: `${t.when}. ${w.band[t.band]}. ${t.lines.join('. ')}.` };
  } else anchor.current = null;
  const switches = [
    points.some((p) => bandOf(p.band) === 'g') && 'g',
    points.some((p) => bandOf(p.band) === 'r') && 'r',
    points.some((p) => p.limit) && 'lim',
    forecasts.length > 0 && 'fc',
  ].filter(Boolean);
  const names0 = { g: w.band.g, r: w.band.r, lim: w.lim, fc: w.fc, ...legend };
  const help = `${id}help`;

  return (
    <div className="figure" ref={ref}>
      <div className="plot" ref={plot} tabIndex={0} role="application" aria-label={label} aria-describedby={help} onKeyDown={key}
        onBlur={() => { if (pick && pick.how === 'key') setPick(null); }}>
        <svg ref={svg} className={`live${zoomed ? ' zoomed' : ''}`} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={cancel}
          onPointerLeave={(e) => { if (e.pointerType === 'mouse' && !drag.current.start && pick && pick.how === 'hover') setPick(null); }}>
          <defs><clipPath id={clip}><rect x={L} y={T} width={R - L} height={B - T} /></clipPath></defs>
          {out}
        </svg>
        {tip && (
          <div className="tip" ref={tipBox} aria-hidden="true">
            <span className="when">{tip.t.when}</span>
            <b className={`band-${tip.t.band}`}>{w.band[tip.t.band]}</b>
            {tip.t.lines.map((s) => <span key={s}>{s}</span>)}
          </div>
        )}
        <p id={help} className="hidden">{w.keys}</p>
        <p className="hidden" aria-live="polite">{tip ? tip.text : ''}</p>
      </div>
      <div className="figbar">
        <div className="legend" role="group" aria-label={w.show}>
          {switches.map((k) => (
            <button key={k} type="button" aria-pressed={!hidden[k]} onClick={() => setHidden((h) => ({ ...h, [k]: !h[k] }))}>
              <Mark k={k} />{names0[k]}
            </button>
          ))}
          {keys.map((k) => <span key={k.text} className="static">{k.mark}{k.text}</span>)}
        </div>
        <div className="views">
          <div className="seg" role="group" aria-label={w.scale}>
            <button type="button" aria-pressed={!mag} onClick={() => setMode('flux')}>{w.flux}</button>
            <button type="button" aria-pressed={mag} onClick={() => setMode('mag')}>{w.mag}</button>
          </div>
          <button type="button" className="btn" disabled={!zoomed} onClick={() => setView(null)}>{w.full}</button>
        </div>
      </div>
    </div>
  );
}
