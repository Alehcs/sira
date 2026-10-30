import { useEffect, useRef, useState } from 'react';
import { Board, Book, Person, Sleep, Window } from './pixel.jsx';
import { WORDS, format } from './words.js';

// which room acts at each step, and which sealed forecast, physics fit and bet it shows
const ROLES = ['dome', 'theory', 'skeptics', 'director', 'forecaster', 'sky', 'leverrier', 'leverrier', 'sky', 'theory', 'director', 'forecaster', 'sky', 'leverrier'];
const SHOWN = ['cp1', 'cp1', 'cp1', 'cp1', 'cp1', 'cp1', 'cp2', 'leap', 'leap', 'cp4', 'cp5', 'cp5', 'cp5', 'cp5'];
const FIT_AT = [0, 0, 0, 0, 0, 1, 1, 1, 2, 3, 4, 4, 4, 4];
const BET_AT = [-1, -1, -1, -1, 0, 1, 1, 1, 2, 2, 3, 4, 4, 4];
const COLORS = { dome: '#5CE1E6', theory: '#FF9F43', skeptics: '#C49BFF', forecaster: '#7CF29C', director: '#FFD447', leverrier: '#FF6AD5', sky: '#F2F0FF' };
const LETTERS = { dome: 'L', theory: 'T', skeptics: 'S', forecaster: 'F', director: 'D', leverrier: 'V', sky: '★' };
const HUE = { ia: '#7B96FF', ibc: '#8A88B0', ii: '#D9A47C', tde: '#C49BFF', null: '#5C5A85', adopted: '#FF9F43' };
const SHORT = { ia: 'Ia', ibc: 'Ibc', ii: 'II', tde: 'TDE' };

function join(lang, items) {
  if (items.length < 2) return items.join('');
  const last = items[items.length - 1];
  const and = lang === 'es' ? (/^I[a-z]/.test(last) ? 'e' : 'y') : 'and';
  return `${items.slice(0, -1).join(', ')} ${and} ${last}`;
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const roughly = (p) => { const x = 1 / p; const e = 10 ** Math.floor(Math.log10(x)); return Math.round(x / e) * e; };

function story(lang, d) {
  const f = format(lang);
  const k = d.facts;
  const b = d.bets;
  const es = lang === 'es';
  const hyps = Object.entries(b[0].weights).filter(([h, v]) => h !== 'null' && v >= 0.005).sort((x, y) => y[1] - x[1]);
  const fits = join(lang, hyps.map(([h, v], i) => `${i ? '' : es ? 'tipo ' : 'type '}${SHORT[h]} ${f.pct(v)}`));
  const none = f.pct(b[0].weights.null || 0);
  const doubts = join(lang, k.skeptics.physics.replace('doubts ', '').split(', ').map((h) => SHORT[h] || h));
  const odds = roughly(k.surprise.p_value).toLocaleString(es ? 'es-CL' : 'en-US');
  const right = (b[4].p >= 0.5) === k.answer;
  const lensVoice = f.pct(b[3].weights.adopted);
  if (es) {
    return {
      events: [
        `Spark Open lee las primeras imágenes, del ${f.day(d.first_detection)}. Ve restas fallidas en todo el campo y le da a la fuente un ${f.pct(k.reader)} de ser real.`,
        `Tres teóricos defienden ${join(lang, k.theories.map((h) => SHORT[h]))}. Los ajustes físicos dan ${fits}, y un ${none} queda en ninguna de las anteriores.`,
        `El escéptico del instrumento contradice al lector: la fuente es real. El de física duda de ${doubts}. El de memoria no reconoce el objeto.`,
        'El director espera las próximas noches de ZTF, que no cuestan nada, y apuesta a la pregunta más informativa: ¿más brillante en r en tres días?',
        `El pronosticador lo expresa como ${f.term(b[0].term)}, ${f.pct(b[0].p)}, y la apuesta queda sellada.`,
        'El cielo responde: más brillante. Pero los puntos nuevos caen por encima del pronóstico de la física.',
        `Cinco días después, ${k.surprise.misses} de ${k.surprise.n} mediciones caen muy fuera del pronóstico. Por azar pasaría una vez en ${odds}. Despierta Le Verrier.`,
        `Tres Le Verrier con Wonder proponen un componente oculto, un modelo nuevo y una falla del instrumento. Lo que mejor explica el pasado es una lente invisible delante de la estrella («${f.name(k.chosen)}»), y se sella contra las hipótesis viejas.`,
        `${k.verdict.n} mediciones nuevas: la estrella llega a su máximo y empieza a bajar, como predijo la lente. log10 E = ${f.num(k.verdict.log10_e)} a favor de la lente: Neptuno.`,
        `La lente entra al lab como hipótesis y se queda con el ${lensVoice} de la voz. Ahora un teórico la defiende.`,
        'El director apuesta donde SIRA podría quedar en evidencia: ¿más brillante en tres días? Un sí refutaría la lente.',
        `${cap(f.term(b[4].term))}, dice el pronosticador: ${f.pct(b[4].p)}. Sellada.`,
        `El cielo responde: ${k.answer ? 'más brillante' : 'más débil'}, ${right ? 'como predijo la lente' : 'contra la lente'}.`,
        `El veredicto sobre la segunda idea de Le Verrier es ${k.second.verdict === 'abstain' ? 'abstención' : k.second.verdict}: no agrega nada a la lente adoptada. La investigación completa costó ${f.money(k.cost)} en ${k.calls} llamadas a Muse.`,
      ],
      says: [`¿Una resta fallida? ${f.pct(k.reader)} real.`, 'Una Ia enrojecida, todavía subiendo.', 'Es real. No es la cámara.', 'Esperamos. Es gratis.',
        `${cap(f.term(b[0].term))}.`, 'Más brillante de lo previsto.', 'Esto no lo predijimos.', 'Una lente invisible delante de una estrella.',
        'Neptuno: la lente acertó.', 'Ahora defendemos la lente.', 'Un sí nos dejaría en evidencia.', `${cap(f.term(b[4].term))}: ${f.pct(b[4].p)}.`,
        right ? 'Más débil, como dijo la lente.' : 'La lente falló.', 'Nada nuevo que inventar.'],
    };
  }
  return {
    events: [
      `Spark Open reads the first images, from ${f.day(d.first_detection)}. It sees broken subtractions across the field and gives the source a ${f.pct(k.reader)} chance of being real.`,
      `Three theorists defend ${join(lang, k.theories.map((h) => SHORT[h]))}. The physics fits give ${fits}, and ${none} stays on none of the above.`,
      `The instrument skeptic contradicts the reader: the source is real. The physics skeptic doubts ${doubts}. The memory skeptic does not recognize the object.`,
      'The director waits for the next ZTF nights, which cost nothing, and bets on the most informative question: brighter in r in three days?',
      `The forecaster words it as ${f.term(b[0].term)}, ${f.pct(b[0].p)}, and the bet is sealed.`,
      'The sky answers: brighter. But the new points land above the physics forecast.',
      `Five days later, ${k.surprise.misses} of ${k.surprise.n} measurements fall far outside the forecast. By luck that happens about once in ${odds} times. Le Verrier wakes up.`,
      `Three Le Verriers on Wonder propose a hidden component, a new model and an instrument fault. The best fit to the past is an invisible lens in front of the star (“${f.name(k.chosen)}”), sealed against the old hypotheses.`,
      `${k.verdict.n} new measurements: the star peaks and turns over, as the lens predicted. log10 E = ${f.num(k.verdict.log10_e)} in favor of the lens: Neptune.`,
      `The lens joins the lab as a hypothesis and takes ${lensVoice} of the voice. A theorist now defends it.`,
      'The director bets where SIRA could be proven wrong: brighter in three days? A yes would refute the lens.',
      `${cap(f.term(b[4].term))}, says the forecaster: ${f.pct(b[4].p)}. Sealed.`,
      `The sky answers: ${k.answer ? 'brighter' : 'fainter'}, ${right ? 'as the lens predicted' : 'against the lens'}.`,
      `The verdict on Le Verrier’s second idea is ${k.second.verdict}: it adds nothing to the adopted lens. The whole investigation cost ${f.money(k.cost)} in ${k.calls} Muse calls.`,
    ],
    says: [`A bad subtraction? ${f.pct(k.reader)} real.`, 'A reddened Ia, still rising.', 'It is real. Not the camera.', 'We wait. It is free.',
      `${cap(f.term(b[0].term))}.`, 'Brighter than forecast.', 'We did not predict this.', 'An invisible lens in front of a star.',
      'Neptune: the lens was right.', 'Now we defend the lens.', 'A yes would prove us wrong.', `${cap(f.term(b[4].term))}: ${f.pct(b[4].p)}.`,
      right ? 'Fainter, as the lens said.' : 'The lens missed.', 'Nothing new to invent.'],
  };
}

function Chart({ d, step, w }) {
  const hi = Math.max(...d.now) + 1.5;
  const X = (x) => 40 + ((x + 3) / (hi + 3)) * 540;
  const Y = (v) => 250 - ((Math.log10(Math.max(40, Math.min(v, 1500))) - Math.log10(40)) / Math.log10(1500 / 40)) * 240;
  const xy = (x, v) => `${X(x).toFixed(0)},${Y(v).toFixed(0)}`;
  const fan = (rows, color, label) => {
    if (!rows) return null;
    const up = rows.map(([x, m, s]) => xy(x, m + 1.645 * s));
    const lo = rows.slice().reverse().map(([x, m, s]) => xy(x, m - 1.645 * s));
    const [x, m, s] = rows[rows.length - 1];
    return (
      <g key={label}>
        <polygon points={up.concat(lo).join(' ')} fill={color} fillOpacity="0.3" />
        <polyline points={rows.map(([x2, m2]) => xy(x2, m2)).join(' ')} fill="none" stroke={color} strokeWidth="3" />
        <text x={X(x).toFixed(0)} y={(Y(m + 1.645 * s) - 6).toFixed(0)} textAnchor="end" fill={color} fontSize="14">{label}</text>
      </g>
    );
  };
  const key = SHOWN[step];
  const ia = key === 'leap' ? d.fans.old : key === 'cp1' || key === 'cp2' ? d.fans[key] : null;
  const lens = key === 'leap' ? d.fans.lens : key === 'cp4' || key === 'cp5' ? d.fans[key] : null;
  const squares = (pts) => pts.map(([x, v]) => `M${(X(x) - 4).toFixed(0)} ${(Y(v) - 4).toFixed(0)}h8v8h-8z`).join(' ');
  const t1 = d.now[step];
  const t0 = d.sealed_at[step];
  const start = new Date(d.first_detection);
  const offset = (start.getUTCHours() * 3600 + start.getUTCMinutes() * 60) / 86400;
  const ticks = [0, 11, 21, 31].map((n) => ({ x: X(n - offset), at: new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate() + n)).toISOString() }));
  const f = format(w.lang);
  return (
    <svg viewBox="0 0 600 280" style={{ width: '100%', height: 'auto', display: 'block' }} shapeRendering="crispEdges" role="img" aria-label={w.chartLabel(d.object)}>
      <rect x="40" y="10" width="540" height="240" fill="#0B0B1A" />
      <line x1="40" y1="250" x2="580" y2="250" stroke="#3C3A6B" strokeWidth="2" />
      {fan(ia, '#7B96FF', w.fan.ia)}
      {fan(lens, '#FF9F43', w.fan.lens)}
      <line x1={X(t1)} y1="10" x2={X(t1)} y2="250" stroke="#F2F0FF" strokeWidth="2" strokeDasharray="6 6" />
      <text x={X(t1) - 8} y="244" textAnchor="end" fill="#F2F0FF" fontSize="14">{w.now}</text>
      <text x="50" y="28" fill="#B8B4E0" fontSize="14">{w.brightness}</text>
      <path d={squares(d.points.filter((p) => p[2] <= t0))} fill="#F2F0FF" />
      <path d={squares(d.points.filter((p) => p[2] > t0 && p[2] <= t1))} fill="#5CE1E6" />
      {ticks.map((t) => <text key={t.at} x={t.x} y="272" textAnchor="middle" fill="#B8B4E0" fontSize="14">{f.short(t.at)}</text>)}
    </svg>
  );
}

function Room({ id, title, model, active, wide, children, say }) {
  return (
    <article className={`room${wide ? ' wide' : ''}`} style={{ borderColor: active ? COLORS[id] : undefined }}>
      <div><h3>{title}</h3><span className="model">{model}</span></div>
      {children}
      <div className="say">{active && <span className="bubble">{say}</span>}</div>
    </article>
  );
}

export default function Lab({ lang, data: d }) {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef(null);
  const last = ROLES.length - 1;
  const w = { ...WORDS[lang].lab, lang };
  const f = format(lang);
  const text = story(lang, d);
  const role = ROLES[step];
  const on = (id) => role === id;

  useEffect(() => {
    if (!playing) return undefined;
    timer.current = setInterval(() => setStep((s) => {
      if (s >= last) { setPlaying(false); return s; }
      return s + 1;
    }), 2500);
    return () => clearInterval(timer.current);
  }, [playing, last]);

  const at = (n) => new Date(new Date(d.first_detection).getTime() + d.now[n] * 86400000).toISOString();
  const fit = d.bets[FIT_AT[step]];
  const voices = Object.entries(fit.weights).filter(([, v]) => v >= 0.005).sort((x, y) => (x[0] === 'null') - (y[0] === 'null') || y[1] - x[1]);
  const held = BET_AT[step] >= 0 ? d.bets[BET_AT[step]] : null;
  const k = d.facts;
  const play = () => {
    if (playing) { setPlaying(false); return; }
    if (step >= last) setStep(0);
    setPlaying(true);
  };

  return (
    <div className="cols">
      <section className="main" aria-label={w.timeMachine}>
        <div className="rooms">
          <Room id="dome" title={w.dome} model="Spark Open" active={on('dome')} wide say={text.says[step]}>
            <div className="scene">
              <Person hat="#5CE1E6" bob={on('dome')} />
              <figure className="stamps">
                <img src={`${import.meta.env.BASE_URL}replays/stamps.png`} alt={w.stampsAlt(d.object)} />
                <div>{w.panels.map((p) => <span key={p}>{p}</span>)}</div>
              </figure>
            </div>
            <span style={{ color: '#5CE1E6' }}>{w.real(f.pct(k.reader))}</span>
          </Room>

          <Room id="theory" title={w.theory} model="Spark 1.3 high" active={on('theory')} say={text.says[step]}>
            <div className="scene">
              {fit.theories.map((h, i) => <Person key={`${h}-${i}`} hat={HUE[h]} bob={on('theory')} delay={i * 0.2} />)}
            </div>
            <div style={{ minHeight: 96, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 15 }}>
              {voices.map(([h, v]) => (
                <div key={h} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div className="row" style={{ color: h === 'null' ? '#B8B4E0' : HUE[h] }}><span>{w.hyp[h] || h}</span><span>{f.pct(v)}</span></div>
                  <div className="bar"><div style={{ width: `${v * 100}%`, background: HUE[h] || '#5C5A85' }} /></div>
                </div>
              ))}
            </div>
          </Room>

          <Room id="skeptics" title={w.skeptics} model="Spark 1.3 high" active={on('skeptics')} say={text.says[step]}>
            <div className="scene" style={{ gap: 14 }}>
              {w.lenses.map((lens, i) => (
                <div key={lens} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                  <Person hat="#C49BFF" skin={['#F2C9A0', '#D9A47C', '#A9735A'][i]} bob={on('skeptics')} delay={i * 0.2} />
                  <span className="muted" style={{ fontSize: 13 }}>{lens}</span>
                </div>
              ))}
            </div>
          </Room>

          <Room id="forecaster" title={w.forecaster} model="Spark 1.3 minimal" active={on('forecaster')} say={text.says[step]}>
            <div className="scene"><Person hat="#7CF29C" bob={on('forecaster')} /><Book /></div>
            <div style={{ minHeight: 44, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {held && <span className="arcade" style={{ fontSize: 14, color: '#7CF29C' }}>{f.pct(held.p)}</span>}
              {held && <span className="mono muted" style={{ fontSize: 13 }}>sha256 {held.hash}…</span>}
            </div>
          </Room>

          <Room id="director" title={w.director} model="Spark 1.3 xhigh" active={on('director')} say={text.says[step]}>
            <div className="scene">
              <Person hat="#FFD447" coat="#3C3A6B" legs="#1B1A2E" bob={on('director')} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, flex: 1 }}>
                {w.choices.map((c, i) => <span key={c} className={`chip${step >= 3 && i === 0 ? ' on' : ''}`}>{c}</span>)}
              </div>
            </div>
          </Room>

          <Room id="leverrier" title={w.leverrier} model="Wonder high" active={on('leverrier')} say={text.says[step]}>
            <div className="scene" style={{ gap: 10 }}>
              <Board />
              <Person hat="#FF6AD5" bob={on('leverrier')} opacity={on('leverrier') ? 1 : step < 6 ? 0.45 : 0.75} />
              {step < 6 && <Sleep label={w.asleep} />}
            </div>
            <ul style={{ minHeight: 84, margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 14 }}>
              {step >= 7 && k.proposals.map((p) => {
                const chosen = p === k.chosen;
                return (
                  <li key={p} style={{ display: 'flex', gap: 8, alignItems: 'baseline', color: chosen ? '#FF6AD5' : '#B8B4E0' }}>
                    <span aria-hidden="true" style={{ flexShrink: 0, width: 8, height: 8, border: `2px solid ${chosen ? '#FF6AD5' : '#B8B4E0'}`, background: chosen ? '#FF6AD5' : 'transparent' }} />
                    {f.name(p)}
                  </li>
                );
              })}
            </ul>
          </Room>

          <Room id="sky" title={w.sky} model="ZTF" active={on('sky')} say={text.says[step]}>
            <div className="scene" style={{ alignItems: 'center' }}><Window /><span style={{ fontSize: 16 }}>{w.measurements(d.counts[step])}</span></div>
            <div style={{ minHeight: 64, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14 }}>
              {step >= 8 && (
                <div className="row" style={{ justifyContent: 'flex-start' }}>
                  <span className="pixel" style={{ padding: '4px 8px', background: '#FF9F43', color: '#0B0B1A', fontSize: 13 }}>{w.neptune}</span>
                  <span style={{ color: '#FF9F43' }}>{w.hyp.adopted}</span>
                  <span className="mono muted" style={{ fontSize: 13 }}>log10 E {f.num(k.verdict.log10_e)}</span>
                </div>
              )}
              {step >= 13 && (
                <div className="row" style={{ justifyContent: 'flex-start' }}>
                  <span className="pixel" style={{ padding: '4px 8px', background: '#3C3A6B', fontSize: 13 }}>{w.abstain}</span>
                  <span className="muted">{w.secondIdea}</span>
                  <span className="mono muted" style={{ fontSize: 13 }}>log10 E {f.num(k.second.log10_e, 2)}</span>
                </div>
              )}
            </div>
          </Room>
        </div>

        <div className="panel">
          <div className="row" style={{ alignItems: 'center' }}>
            <div className="row" style={{ justifyContent: 'flex-start', gap: 16 }}>
              <h2>{w.timeMachine}</h2>
              <span>{f.day(at(step))}</span>
              <span className="mono muted" style={{ fontSize: 14 }}>{f.money(d.spent[step])}</span>
            </div>
            <div className="row" style={{ justifyContent: 'flex-start' }}>
              <button type="button" className="button" onClick={() => { setPlaying(false); setStep(Math.max(step - 1, 0)); }}>{w.back}</button>
              <button type="button" className="button primary" onClick={play}>{playing ? w.pause : w.play}</button>
              <button type="button" className="button" onClick={() => setStep(Math.min(step + 1, last))}>{w.next}</button>
            </div>
          </div>
          <div className="steps" role="group" aria-label={w.timeMachine}>
            {ROLES.map((r, i) => (
              <button type="button" key={i} className={i < step ? 'past' : undefined} aria-current={i === step ? 'step' : undefined}
                aria-label={`${w.step} ${i + 1}: ${w.names[r]}`} onClick={() => { setPlaying(false); setStep(i); }}>{i + 1}</button>
            ))}
          </div>
        </div>
      </section>

      <aside className="side">
        <section className="panel" aria-label={d.object}>
          <h2 style={{ color: '#FFD447' }}>{d.object}</h2>
          <Chart d={d} step={step} w={w} />
        </section>
        <section className="panel" aria-label={w.log}>
          <h2>{w.log}</h2>
          <ol className="log">
            {ROLES.slice(0, step + 1).map((r, i) => ({ r, i })).reverse().map(({ r, i }) => (
              <li key={i} className={i === step ? undefined : 'old'}>
                <span className="mark" style={{ background: COLORS[r] }} aria-hidden="true">{LETTERS[r]}</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <div className="when"><span>{f.day(at(i))}</span><span>{w.names[r]}</span></div>
                  <span style={{ fontSize: 16, lineHeight: 1.4 }}>{text.events[i]}</span>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </aside>
    </div>
  );
}
