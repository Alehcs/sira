import { useId } from 'react';
import { WORDS, format } from '../words.js';
import { useWidth } from './width.js';

const f1 = (v) => v.toFixed(1);
const minus = (v) => String(v).replace('-', '−');
const STEPS = [1, 2, 5, 10, 20, 50, 100, 200];
const MINOR = { 1: 0, 2: 1, 5: 1, 10: 2, 20: 5, 50: 10, 100: 20, 200: 50 };

// a round flux at or beyond v, for the ends of the log axis
function nice(v, up) {
  const e = 10 ** Math.floor(Math.log10(v));
  const steps = [1, 2, 3, 5, 10];
  return e * (up ? steps.find((s) => s * e >= v) : steps.slice().reverse().find((s) => s * e <= v));
}

// the light curve: points {day, band, flux, err, limit}, forecasts {band, rows: [[day, mean, sd]], style, label, hash, place, z}
export default function Figure({ lang, start, points = [], forecasts = [], rings = [], note, now, reference, target, x, y, label }) {
  const [ref, W] = useWidth();
  const clip = `plot${useId().replace(/:/g, '')}`;
  const w = WORDS[lang].fig;
  const f = format(lang);
  const narrow = W < 500;
  const H = narrow ? 300 : Math.round(Math.max(300, Math.min(440, W * 0.64)));
  if (!W) return <div className="figure" ref={ref} style={{ height: H }} />;

  const m = narrow ? { l: 38, r: 38, t: 26, b: start ? 48 : 32 } : { l: 54, r: 48, t: 28, b: start ? 52 : 36 };
  const L = m.l;
  const T = m.t;
  const R = W - m.r;
  const B = H - m.b;
  const days = points.map((p) => p.day).concat(forecasts.flatMap((fc) => fc.rows.map((r) => r[0])), now ?? [], target ? target.day : []);
  const fluxes = points.map((p) => p.flux).concat(forecasts.flatMap((fc) => fc.rows.map((r) => r[1])), reference ? reference.flux : []).filter((v) => v > 0);
  const [x0, x1] = x || [Math.floor(Math.min(...days)) - 1, Math.ceil(Math.max(...days)) + 1];
  const [lo, hi] = y || [nice(Math.min(...fluxes) / 1.3, false), nice(Math.max(...fluxes) * 1.3, true)];
  const X = (d) => L + ((d - x0) / (x1 - x0)) * (R - L);
  const Y = (v) => T + (1 - (Math.log10(Math.max(v, lo / 100)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (B - T);
  const dateOf = (d) => new Date(new Date(start).getTime() + d * 86400000).toISOString();
  const out = [];
  const ticks = [];

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
  const bright = 23.9 - 2.5 * Math.log10(hi);
  const faint = 23.9 - 2.5 * Math.log10(lo);
  const every = faint - bright > 9 ? 2 : 1;
  for (let mag = Math.ceil(bright); mag <= faint; mag += 1) {
    if (mag % every) continue;
    const at = Y(10 ** ((23.9 - mag) / 2.5));
    ticks.push(`M${R} ${f1(at)}h-5`);
    out.push(<text key={`m${mag}`} x={R + 8} y={f1(at + 4)}>{mag}</text>);
  }
  const step = STEPS.find((s) => s * ((R - L) / (x1 - x0)) >= (narrow ? 56 : 60)) || 200;
  const small = MINOR[step] || step;
  for (let d = Math.ceil(x0 / small) * small; d <= x1; d += small) {
    const major = d % step === 0;
    const len = major ? 7 : 3.5;
    ticks.push(`M${f1(X(d))} ${B}v-${len}M${f1(X(d))} ${T}v${len}`);
    if (!major) continue;
    out.push(<text key={`d${d}`} x={f1(X(d))} y={B + 18} textAnchor="middle">{minus(d)}</text>);
    if (start) out.push(<text key={`c${d}`} x={f1(X(d))} y={B + 35} textAnchor="middle">{f.short(dateOf(d))}</text>);
  }
  out.push(<path key="ticks" className="tick" d={ticks.join('')} />);
  out.push(<text key="ujy" x={L - 8} y={T - 11} textAnchor="end">µJy</text>);
  out.push(<text key="ab" x={W - 2} y={T - 11} textAnchor="end">mag AB</text>);
  out.push(<text key="days" x={R + 8} y={B + 18}>{w.days}</text>);

  // forecasts: mean ± z sigma, clipped to the frame, each named at its end with its seal
  const bands = [];
  const names = [];
  forecasts.forEach((fc, i) => {
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
    const lower = fc.place === 'lower';
    const edge = (r) => (lower ? r[1] - z * r[2] : r[1] + z * r[2]);
    const hash = narrow ? '' : fc.hash || '';
    const tw = Math.max(fc.label.length * 7.4, hash ? 60 : 0);
    const end = fc.rows[fc.rows.length - 1];
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
    if (reference.label) out.push(<text key="refl" className="refl" x={L + 8} y={f1(Y(reference.flux) - 6)}>{reference.label}</text>);
  }
  if (target) {
    out.push(<line key="target" className="target" x1={f1(X(target.day))} x2={f1(X(target.day))} y1={T} y2={B} />);
    // the label sits beside its line, never across it
    const right = X(target.day) + 6 + String(target.label || '').length * 8 <= R - 4;
    if (target.label) out.push(<text key="targetl" className="refl" x={f1(X(target.day) + (right ? 6 : -6))} y={T + 16} textAnchor={right ? 'start' : 'end'}>{target.label}</text>);
  }

  // the measurements: one sigma bars, g circles, r squares, open triangles for upper limits
  const err = { g: [], r: [] };
  const lim = { g: [], r: [] };
  const dot = { g: [], r: [] };
  for (const p of points) {
    const b = p.band === 'g' ? 'g' : 'r';
    const px = X(p.day);
    const py = Y(p.flux);
    if (p.limit) {
      lim[b].push(`M${f1(px - 4.5)} ${f1(py - 3.5)}h9l-4.5 8z`);
      continue;
    }
    if (p.err) err[b].push(`M${f1(px)} ${f1(Y(p.flux + p.err))}V${f1(Y(p.flux - p.err))}`);
    dot[b].push(b === 'g' ? `M${f1(px - 3.6)} ${f1(py)}a3.6 3.6 0 1 0 7.2 0a3.6 3.6 0 1 0 -7.2 0z` : `M${f1(px - 3.4)} ${f1(py - 3.4)}h6.8v6.8h-6.8z`);
  }
  out.push(
    <g key="points" clipPath={`url(#${clip})`}>
      <path className="err sg" d={err.g.join('')} /><path className="err sr" d={err.r.join('')} />
      <path className="lim sg" d={lim.g.join('')} /><path className="lim sr" d={lim.r.join('')} />
      <path className="ptg" d={dot.g.join('')} /><path className="ptr" d={dot.r.join('')} />
    </g>,
  );
  for (const r of rings) out.push(<circle key={`r${r.day}`} className="ring" cx={f1(X(r.day))} cy={f1(Y(r.flux))} r="8.5" />);
  if (note && rings.length) {
    const nx = X(Math.min(...rings.map((r) => r.day))) - 7;
    const ny = Y(Math.max(...rings.map((r) => r.flux))) - (narrow ? 38 : 22);
    out.push(<text key="note" className="warn" x={f1(nx)} y={f1(ny)} textAnchor="end">{note.text}</text>);
    if (note.sub && !narrow) out.push(<text key="notes" x={f1(nx)} y={f1(ny + 16)} textAnchor="end">{note.sub}</text>);
  }

  // each band named once, at its first detection
  for (const b of ['r', 'g']) {
    const p = points.find((q) => q.band === b && !q.limit);
    if (p) out.push(<text key={`b${b}`} className={`band-${b}`} x={f1(X(p.day) - 9)} y={f1(Y(p.flux) + 5)} textAnchor="end">{b}</text>);
  }

  if (now !== undefined && now !== null) {
    const right = X(now) + 7 + 46 <= R - 4;
    const at = { x: f1(right ? X(now) + 7 : X(now) - 7), textAnchor: right ? 'start' : 'end' };
    out.push(<line key="now" className="now" x1={f1(X(now))} x2={f1(X(now))} y1={T} y2={B} />);
    out.push(<text key="nowt" {...at} y={start ? B - 24 : B - 9}>{w.now}</text>);
    if (start) out.push(<text key="nowd" className="nowl" {...at} y={B - 9}>{f.short(dateOf(now))}</text>);
  }
  out.push(<rect key="frame" className="frame" x={L + 0.5} y={T + 0.5} width={R - L - 1} height={B - T - 1} />);

  return (
    <div className="figure" ref={ref}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        <defs><clipPath id={clip}><rect x={L} y={T} width={R - L} height={B - T} /></clipPath></defs>
        {out}
      </svg>
    </div>
  );
}
