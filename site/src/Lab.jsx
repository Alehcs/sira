import { useEffect, useMemo, useState } from 'react';
import Dome from './ui/Dome.jsx';
import { lengths } from './ui/dome/script.js';
import Figure from './ui/Figure.jsx';
import Paper from './ui/Paper.jsx';
import Stamps from './ui/Stamps.jsx';
import { Message, Thread } from './ui/Thread.jsx';
import { WORDS, format } from './words.js';

const BASE = import.meta.env.BASE_URL;
// who speaks at each step, which sealed forecast the figure shows and which bet's fit weighs the hypotheses
const ROLES = ['dome', 'theory', 'skeptics', 'director', 'forecaster', 'sky', 'leverrier', 'leverrier', 'sky', 'theory', 'director', 'forecaster', 'sky', 'leverrier'];
const SHOWN = ['cp1', 'cp1', 'cp1', 'cp1', 'cp1', 'cp1', 'cp2', 'leap', 'leap', 'cp4', 'cp5', 'cp5', 'cp5', 'cp5'];
const FIT_AT = [0, 0, 0, 0, 0, 1, 1, 1, 2, 3, 4, 4, 4, 4];
const MODELS = { dome: 'Spark Open', theory: 'Spark 1.3 high', skeptics: 'Spark 1.3 high', director: 'Spark 1.3 xhigh', forecaster: 'Spark 1.3 minimal', sky: 'ZTF', leverrier: 'Wonder high' };
const SHORT = { ia: 'Ia', ibc: 'Ibc', ii: 'II', tde: 'TDE' };
// sky.jpg is a lossless crop of the Pan-STARRS1 field at 0.262″ a pixel, with the object at (736, 210)
const FIELD = { at: [736, 210] };
// in the observatory: whom the sky and Le Verrier speak to at each of their steps
const TO = { 5: ['director'], 6: ['director'], 7: ['forecaster'], 8: ['leverrier'], 12: ['forecaster'] };
const E = <span className="mono">log<sub>10</sub>{' '}<i className="v">E</i></span>;

function join(lang, items) {
  if (items.length < 2) return items.join('');
  const last = items[items.length - 1];
  const and = lang === 'es' ? (/^I[a-z]/.test(last) ? 'e' : 'y') : 'and';
  return `${items.slice(0, -1).join(', ')} ${and} ${last}`;
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const roughly = (p) => { const x = 1 / p; const e = 10 ** Math.floor(Math.log10(x)); return Math.round(x / e) * e; };

function story(lang, d, f) {
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
        <>{k.verdict.n} mediciones nuevas: la estrella llega a su máximo y empieza a bajar, como predijo la lente. {E} = {f.num(k.verdict.log10_e)} a favor de la lente: <b className="ok">Neptuno</b>.</>,
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
      <>{k.verdict.n} new measurements: the star peaks and turns over, as the lens predicted. {E} = {f.num(k.verdict.log10_e)} in favor of the lens: <b className="ok">Neptune</b>.</>,
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

// each step as the observatory plays it: the calls behind it, who says the step's line and what the screens show
function beats(d, says) {
  const F = d.fans;
  const fans = { cp1: F.cp1.r, cp2: F.cp2.r, leap: F.lens.r, cp4: F.cp4.r, cp5: F.cp5.r };
  return ROLES.map((role, i) => {
    const calls = d.calls[i].map((c) => ({ ...c }));
    const weights = d.bets[FIT_AT[i]].weights;
    const theories = calls.filter((c) => c.role === 'theorist');
    const lead = theories.find((c) => c.decision === 'defends adopted')
      || theories.sort((a, b) => (weights[b.decision.slice(8)] || 0) - (weights[a.decision.slice(8)] || 0))[0];
    const speaker = { dome: calls.find((c) => c.role === 'reader'), theory: lead, skeptics: calls.find((c) => c.lens === 'instrument'),
      director: calls.find((c) => c.role === 'director'), forecaster: calls.find((c) => c.role === 'forecaster'),
      leverrier: calls.find((c) => c.role === 'leverrier') }[role];
    if (speaker) Object.assign(speaker, { says: says[i] }, TO[i] && { to: TO[i] });
    else calls.push({ role: role === 'sky' ? 'sky' : 'leverrier', says: says[i], to: TO[i] });
    const now = d.now[i];
    const fan = fans[SHOWN[i]];
    return {
      calls,
      seal: role === 'forecaster' ? (i === 4 ? d.bets[0] : d.bets[d.bets.length - 1]).p : null,
      scene: {
        now, fan, weights, old: SHOWN[i] === 'leap' ? F.old.r : fan, lens: F.lens.r, rival: F.old.r,
        range: { x0: -3, x1: 41, f0: 22, f1: 1600 },
        pts: d.phot.filter((p) => p[2] === 'det' && p[5] <= now + 1e-6).map((p) => [p[0], p[3], p[1]]),
        voices: Object.entries(weights).filter(([, v]) => v >= 0.005).sort((x, y) => (x[0] === 'null') - (y[0] === 'null') || y[1] - x[1]),
      },
    };
  });
}

function Voices({ weights, w, f }) {
  const rows = Object.entries(weights).filter(([, v]) => v >= 0.005).sort((x, y) => (x[0] === 'null') - (y[0] === 'null') || y[1] - x[1]);
  return (
    <div className="voices">
      {rows.map(([h, v]) => (
        <div key={h} className={`v${h === 'null' ? ' null' : ''}`}>
          <span>{w.hyp[h] || h}</span>
          <i aria-hidden="true"><b style={{ width: `${(v * 100).toFixed(1)}%` }} /></i>
          <span className="pct">{f.pct(v)}</span>
        </div>
      ))}
    </div>
  );
}

function Sealed({ bet, now, w, f }) {
  // the sky's answer shows on the record only once it has come
  const a = bet.answer;
  const known = a && !a.void && now >= a.at;
  const right = known && (bet.p >= 0.5) === a.yes;
  return (
    <Paper question={f.question(bet.question)} p={f.pct(bet.p)} term={f.term(bet.term)} hash={bet.hash} time={f.stamp(bet.time)}
      answer={known ? { text: w.answer(a.yes), detail: `${w.score} ${f.num(a.log_score, 2)}`, tone: right ? 'ok' : 'warn' } : null} />
  );
}

function Verdict({ v, line, w, f }) {
  const tone = { neptune: 'ok', vulcan: 'warn' }[v.verdict];
  return (
    <Paper title={w.verdicts[v.verdict]} tone={tone} hash={v.hash} time={f.stamp(v.time)}>
      <p className="line">{line}</p>
      <div className="e">{E} = {f.num(v.log10_e, v.verdict === 'abstain' ? 2 : 1)} {w.inN(v.n)}</div>
    </Paper>
  );
}

function attachment(i, d, step, w, f) {
  const k = d.facts;
  const last = d.bets[d.bets.length - 1];
  if (i === 0) {
    return <Stamps src={`${BASE}replays/stamps.png`} size={[1032, 252]} tile={252} gap={8} pixel={4} scale={2} labels={w.panels} alt={w.stampsAlt(d.object)} arcsec={10} />;
  }
  if (i === 1 || i === 9) return <Voices weights={d.bets[FIT_AT[i]].weights} w={w} f={f} />;
  if (i === 2) {
    const physics = k.skeptics.physics.startsWith('doubts ') ? w.doubts(k.skeptics.physics.slice(7).split(', ').map((h) => w.hyp[h] || h)) : k.skeptics.physics;
    return (
      <dl className="lines">
        <dt>{w.lenses.instrument}</dt><dd>{k.skeptics.instrument === 'artifact' ? w.artifact : w.realSource}</dd>
        <dt>{w.lenses.physics}</dt><dd>{physics}</dd>
        <dt>{w.lenses.memory}</dt><dd>{k.skeptics.memory === 'recognises it' ? w.recognises : w.forgets}</dd>
      </dl>
    );
  }
  if (i === 3 || i === 10) {
    const action = (i === 3 ? d.bets[0] : last).action;
    return <div className="choices">{Object.entries(w.choices).map(([a, name]) => <span key={a} className={a === action ? 'on' : undefined}>{name}</span>)}</div>;
  }
  if (i === 4 || i === 11) return <Sealed bet={i === 4 ? d.bets[0] : last} now={d.now[step]} w={w} f={f} />;
  if (i === 5 || i === 8 || i === 12) {
    return (
      <>
        <div className="count"><b>{w.measurements(d.counts[i])}</b><span>+{d.counts[i] - d.counts[i - 1]}</span></div>
        {i === 8 && <Verdict v={d.leaps[0].verdict} line={w.against(w.hyp.adopted)} w={w} f={f} />}
      </>
    );
  }
  if (i === 6) {
    const p = k.surprise.p_value;
    const e = Math.floor(Math.log10(p));
    return (
      <div className="surprise">
        <b>{w.outside(k.surprise.misses, k.surprise.n)}</b>
        <span><i className="v">p</i> = {f.num(p / 10 ** e, 2)} × 10<sup>{String(e).replace('-', '−')}</sup></span>
        <span>sha256&nbsp;{d.bets[1].hash.slice(0, 8)}…</span>
      </div>
    );
  }
  if (i === 7) {
    const leap = d.leaps[0];
    return (
      <ul className="props">
        {leap.proposals.map((p) => {
          const chosen = p.name === leap.chosen;
          return (
            <li key={p.name} className={chosen ? 'chosen' : undefined}>
              <span className="leap">{w.leaps[p.leap]}</span>
              <span>{f.name(p.name)}{chosen && <span className="seal">{w.chosen}, sha256&nbsp;{leap.hash}…</span>}</span>
              <span className="bic"><span>BIC</span> {f.num(p.bic, 1)}</span>
            </li>
          );
        })}
      </ul>
    );
  }
  if (i === 13 && d.leaps[1]) return <Verdict v={d.leaps[1].verdict} line={w.againstLens(f.name(d.leaps[1].chosen))} w={w} f={f} />;
  return null;
}

export default function Lab({ lang, data: d }) {
  const [step, setStep] = useState(8);
  const [playing, setPlaying] = useState(false);
  const last = ROLES.length - 1;
  const w = WORDS[lang].lab;
  const f = format(lang);
  const text = story(lang, d, f);
  const k = d.facts;
  const at = (n) => new Date(new Date(d.first_detection).getTime() + n * 86400000).toISOString();
  const scenes = useMemo(() => beats(d, text.says), [d, lang]);
  const pace = useMemo(() => lengths(scenes), [scenes]);

  // playing, each step lasts as long as the observatory takes to play it
  useEffect(() => {
    if (!playing) return undefined;
    if (step >= last) { setPlaying(false); return undefined; }
    const timer = setTimeout(() => setStep(step + 1), pace[step] * 1000);
    return () => clearTimeout(timer);
  }, [playing, step, last, pace]);

  const go = (n) => { setPlaying(false); setStep(Math.min(Math.max(n, 0), last)); };
  const play = () => {
    if (playing) { setPlaying(false); return; }
    if (step >= last) setStep(0);
    setPlaying(true);
  };

  // the figure at this step: what the sky had shown by then and the forecast sealed last
  const now = d.now[step];
  const seen = d.phot.filter((p) => p[5] <= now + 1e-6).map(([day, band, kind, flux, err]) => ({ day, band, flux, err, limit: kind === 'lim' }));
  const F = d.fans;
  const h8 = (h) => h.slice(0, 8);
  const sealed = (fan, band, label, hash) => ({ band, rows: fan[band], style: 'sealed', label, hash: hash && h8(hash) });
  const forecasts = {
    cp1: [sealed(F.cp1, 'r', w.fan.ia, d.bets[0].hash)],
    cp2: [sealed(F.cp2, 'g'), sealed(F.cp2, 'r', w.fan.ia, d.bets[1].hash)],
    leap: [{ band: 'g', rows: F.cp2.g, style: 'old' }, { band: 'r', rows: F.cp2.r, style: 'old' },
      { band: 'r', rows: F.old.r, style: 'rival', label: w.fan.ia, hash: h8(d.leaps[0].hash), place: 'lower' }, sealed(F.lens, 'r', w.fan.lens, d.leaps[0].hash)],
    cp4: [sealed(F.cp4, 'r', w.fan.lens, d.bets[3].hash)],
    cp5: [sealed(F.cp5, 'r', w.fan.lens, d.bets[4].hash)],
  }[SHOWN[step]];
  const missed = step >= 6 && step <= 8;

  // the steps grouped under their dates, in one row on wide screens and two rows of seven on phones
  const dates = ROLES.map((r, i) => f.short(at(d.now[i])));
  const button = (i) => (
    <button key={i} type="button" className={i < step ? 'past' : undefined} aria-current={i === step ? 'step' : undefined}
      aria-label={`${w.step} ${i + 1}: ${w.names[ROLES[i]]}`} onClick={() => go(i)}>{i + 1}</button>
  );
  const groups = [];
  dates.forEach((label, i) => {
    if (!groups.length || groups[groups.length - 1].label !== label) groups.push({ label, items: [] });
    groups[groups.length - 1].items.push(i);
  });
  const halves = [[0, 7], [7, 14]].map(([a, b]) => {
    const ids = ROLES.map((r, i) => i).slice(a, b);
    const spans = [];
    ids.forEach((i) => {
      if (spans.length && spans[spans.length - 1].label === dates[i]) spans[spans.length - 1].n += 1;
      else spans.push({ label: dates[i], n: 1, i });
    });
    return { ids, spans };
  });

  return (
    <>
      <Dome lang={lang} beats={scenes} at={step} sky={{ src: `${BASE}replays/sky.jpg`, at: FIELD.at }}
        stamps={{ src: `${BASE}replays/stamps.png`, tile: 252, gap: 8, pixel: 4 }} />
      <div className="objhead">
        <h1>{d.object}</h1>
        <div className="coords">
          <span><b>{f.ra(d.ra)} {f.dec(d.dec)}</b></span>
          <span>l {f.num(d.l, 2)}° b {d.b >= 0 ? '+' : ''}{f.num(d.b, 2)}°</span>
          <span>{w.first} {f.stamp(d.first_detection)}</span>
          <span>MJD {f.num(d.mjd, 2)}</span>
        </div>
      </div>
      <div className="lab">
        <Thread lang={lang} label={w.thread} current={step}>
          {ROLES.slice(0, step + 1).map((r, i) => (
            <Message key={i} mark={w.marks[r]} name={w.names[r]} model={r === 'leverrier' && d.spent[i] === d.spent[i - 1] ? null : MODELS[r]}
              when={f.day(at(d.now[i]))} at={at(d.now[i])} cost={f.money(d.spent[i])} says={text.says[i]} text={text.events[i]}
              quote={d.said[i] ? { text: d.said[i], lang: 'en' } : null} current={i === step}>
              {attachment(i, d, step, w, f)}
            </Message>
          ))}
        </Thread>
        <section className="fig">
          <Figure lang={lang} start={d.first_detection} points={seen} forecasts={forecasts} now={now} x={[-31, 41]} y={[10, 3000]}
            rings={missed ? d.misses.map(([day, , flux]) => ({ day, flux })) : []}
            note={missed ? { text: w.outside(k.surprise.misses, k.surprise.n), sub: `${w.fan.ia} ${h8(d.bets[1].hash)}` } : null}
            label={w.chartLabel(d.object)} />
          <div className="ctrl">
            <button type="button" className="btn" disabled={step === 0} onClick={() => go(step - 1)}>{w.back}</button>
            <button type="button" className="btn primary" onClick={play}>{playing ? w.pause : w.play}</button>
            <button type="button" className="btn" disabled={step === last} onClick={() => go(step + 1)}>{w.next}</button>
            <div className="state">
              <span>{w.stepOf[0]} <b>{step + 1}</b> {w.stepOf[1]} {ROLES.length}</span>
              <b>{f.day(at(now))}</b>
              <b>{f.money(d.spent[step])}</b>
            </div>
          </div>
          <div className="scrub" role="group" aria-label={w.timeMachine}>
            {groups.map((g) => <div key={g.label} className="grp"><div>{g.items.map(button)}</div><span>{g.label}</span></div>)}
          </div>
          <div className="pscrub" role="group" aria-label={w.timeMachine}>
            {halves.flatMap((h) => [...h.ids.map(button), ...h.spans.map((s) => <span key={`d${s.i}`} style={{ gridColumn: `span ${s.n}` }}>{s.label}</span>)])}
          </div>
        </section>
      </div>
    </>
  );
}
