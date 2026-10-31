import { useEffect, useState } from 'react';
import Figure from './ui/Figure.jsx';
import Paper from './ui/Paper.jsx';
import Stamps from './ui/Stamps.jsx';
import { useWidth } from './ui/width.js';
import { supabase } from './supabase.js';
import { WORDS, format } from './words.js';

const BASE = import.meta.env.BASE_URL;
const LEVEL = /^(Brighter|Fainter) than ([\d.]+) microjansky in (\w) (\d+) days from now\?$/;
const toMjd = (iso) => new Date(iso).getTime() / 86400000 + 40587;
const ALIAS = /^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{2,24}$/; // the same rule the database keeps
const WINDOW = 40; // days of light curve shown before a round opens
const KEPT = 'practice';

function fields(q) {
  const m = LEVEL.exec(q.text);
  if (m) return { kind: 'level', direction: m[1] === 'Brighter' ? 'above' : 'below', reference: Number(m[2]), band: m[3], days: Number(m[4]) };
  return { kind: 'last', direction: 'above', reference: Math.round(q.reference * 10) / 10, band: (q.band || 'ztfr').slice(-1), days: 3 };
}

const points = (rows, shift = 0) => rows
  .map(([day, band, kind, flux, err]) => ({ day: day - shift, band: band.slice(-1), flux, err, limit: kind !== 'det' }))
  .filter((p) => p.flux > 0);
const micro = (v, f) => `${f.num(v, Number.isInteger(v) ? 0 : 1)} µJy`;
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

function recall() {
  try {
    const kept = JSON.parse(localStorage.getItem(KEPT));
    if (kept && Number.isInteger(kept.at) && kept.said && typeof kept.said === 'object') return kept;
  } catch (e) { /* storage can be blocked */ }
  return { at: 0, said: {} };
}

function countdown(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor(s / 60) % 60;
  if (h) return `${h} h ${m} min`;
  return m ? `${m} min ${s % 60} s` : `${s} s`;
}

// the three cutouts at the largest whole scale that fits the column, two to a row when three would be too small
function Strip({ src, panel, w, alt }) {
  const [ref, W] = useWidth();
  const fit = Math.floor((W - 8) / (3 * panel[0]));
  const scale = Math.min(3, fit >= 2 ? fit : W >= 2 * panel[0] + 4 ? 2 : 1);
  return (
    <div className="strip" ref={ref}>
      {W > 0 && <Stamps src={src} size={[panel[0] * 3, panel[1]]} tile={panel[0]} scale={scale} labels={w.panels} alt={alt} arcsec={10} />}
    </div>
  );
}

function Slider({ value, set, disabled, w, f }) {
  const p = value / 100;
  return (
    <div className="slider">
      <label>
        <span className="you"><span>{w.you}</span><b>{f.pct(p)}</b></span>
        <input type="range" min="1" max="99" value={value} disabled={disabled} onChange={(e) => set(Number(e.target.value))} />
      </label>
      <div className="ends" aria-hidden="true"><span>{w.no}</span><span>{w.yes}</span></div>
      <p className="scores">
        <span>{w.score}</span>
        <span>{w.ifYes} <b>{f.num(Math.log(p), 2)}</b></span>
        <span>{w.ifNo} <b>{f.num(Math.log(1 - p), 2)}</b></span>
      </p>
    </div>
  );
}

function Live({ q, i, img, value, set, betted, closes, lang, w, f }) {
  const opens = toMjd(q.opens_at);
  const ask = fields(q);
  const seen = points(q.seen || [], opens).filter((p) => p.day >= -WINDOW);
  const target = q.mjd - opens;
  return (
    <article className="ask">
      <div className="top">
        <p className="nth"><b>{w.q} {i + 1}</b><span>{q.object}</span></p>
        <p className="text">{f.question(ask)}</p>
        {img && img.stamps && <Strip src={BASE + img.stamps} panel={img.panel} w={w} alt={w.stampsAlt(q.object)} />}
      </div>
      <div className="fig">
        <Figure lang={lang} start={q.opens_at} points={seen} x={[Math.floor(Math.min(target, ...seen.map((p) => p.day))) - 1, Math.ceil(target) + 3]}
          reference={{ flux: ask.reference, label: micro(ask.reference, f) }}
          target={{ day: target, label: w.inDays(ask.days) }} label={w.chart(q.object)} />
      </div>
      <div className="pick">
        <Slider value={value} set={set} disabled={betted} w={w} f={f} />
        <Paper hash={q.commit.slice(0, 12)}><p className="line"><b>{w.sira}</b> {w.sealed(closes)}</p></Paper>
      </div>
    </article>
  );
}

function Reveal({ q, said, shown, w, f }) {
  const a = q.answer;
  const mine = Math.log(a.yes ? said : 1 - said);
  const lead = mine - a.log_score;
  const result = lead > 1e-9 ? { text: w.won, tone: 'ok' } : lead < -1e-9 ? { text: w.lost, tone: 'warn' } : { text: w.tie };
  return (
    <>
      <Paper title={w.skyAnswer(a.yes)} answer={result}>
        <table className="vs">
          <thead><tr><th /><th>{w.said}</th><th>{w.score}</th></tr></thead>
          <tbody>
            <tr><td>{w.you}</td><td>{f.pct(said)}</td><td>{f.num(mine, 2)}</td></tr>
            <tr><td>{w.sira}</td><td>{f.pct(a.sira)}</td><td>{f.num(a.log_score, 2)}</td></tr>
          </tbody>
        </table>
      </Paper>
      {shown && (
        <div className="who">
          {shown.host && <img src={BASE + shown.host} width="128" height="128" alt={w.hostAlt(shown.object)} />}
          <div>
            <p className="oid">{shown.object}</p>
            <p>{a.class}</p>
            <a href={shown.alerce}>ALeRCE</a>
          </div>
        </div>
      )}
    </>
  );
}

function Practice({ bank, lang, w, f }) {
  const [kept, setKept] = useState(recall);
  const [value, setValue] = useState(50);
  const qs = bank.questions;
  const at = Math.min(kept.at, qs.length);
  const q = qs[at];
  const said = q ? kept.said[q.label] : undefined;
  const keep = (next) => {
    setKept(next);
    try { localStorage.setItem(KEPT, JSON.stringify(next)); } catch (e) { /* storage can be blocked */ }
  };
  const go = (next) => { keep(next); setValue(50); };

  // the running tally, on the questions answered so far
  const done = qs.filter((x) => kept.said[x.label] !== undefined);
  const yours = done.map((x) => Math.log(x.answer.yes ? kept.said[x.label] : 1 - kept.said[x.label]));
  const siras = done.map((x) => x.answer.log_score);
  const beaten = yours.filter((v, i) => v - siras[i] > 1e-9).length;

  let card = null;
  if (q) {
    const after = said === undefined ? [] : points(q.answer.after);
    const seen = points(q.ask.seen);
    const days = q.ask.seen.concat(q.answer.after).map((r) => r[0]).concat(q.ask.days);
    card = (
      <article className="ask">
        <div className="top">
          <p className="nth"><b>{w.nth(at + 1, qs.length)}</b>{q.step > 1 && <span>{w.again}</span>}</p>
          <p className="text">{f.question(q.ask)}</p>
          <Strip src={BASE + q.ask.stamps} panel={q.ask.panel} w={w} alt={w.practiceStamps} />
        </div>
        <div className="fig">
          <Figure lang={lang} points={seen.concat(after)} x={[Math.floor(Math.min(...days)) - 1, Math.ceil(Math.max(...days)) + 2]}
            reference={{ flux: q.ask.reference, label: micro(q.ask.reference, f) }}
            target={{ day: q.ask.days, label: w.inDays(q.ask.days) }} label={w.practiceChart} />
        </div>
        <div className="pick">
          {said === undefined ? (
            <>
              <Slider value={value} set={setValue} w={w} f={f} />
              <button type="button" className="btn primary" onClick={() => keep({ ...kept, said: { ...kept.said, [q.label]: value / 100 } })}>{w.answer}</button>
            </>
          ) : (
            <>
              <Reveal q={q} said={said} shown={bank.reveal.find((r) => r.group === q.group)} w={w} f={f} />
              <button type="button" className="btn primary" onClick={() => go({ ...kept, at: at + 1 })}>{at + 1 < qs.length ? w.next : w.finish}</button>
            </>
          )}
        </div>
      </article>
    );
  }

  return (
    <section className="practice" aria-labelledby="practice">
      <div className="head">
        <h2 id="practice">{w.practice}</h2>
        <dl className="tally">
          <div><dt>{w.answered}</dt><dd>{w.of(done.length, qs.length)}</dd></div>
          <div><dt>{w.yours}</dt><dd>{done.length ? f.num(mean(yours), 2) : '—'}</dd></div>
          <div><dt>{w.siras}</dt><dd>{done.length ? f.num(mean(siras), 2) : '—'}</dd></div>
          <div><dt>{w.beaten}</dt><dd>{w.of(beaten, done.length)}</dd></div>
        </dl>
        <button type="button" className="btn" disabled={!done.length} onClick={() => go({ at: 0, said: {} })}>{w.restart}</button>
      </div>
      {card || <p className="next">{w.done(qs.length)}</p>}
    </section>
  );
}

function LastRound({ round, w, f }) {
  return (
    <section aria-labelledby="last">
      <h2 id="last">{w.last}</h2>
      {!round && <p className="muted">{w.noRound}</p>}
      {round && <p className="when">{f.day(`${round.round}T12:00:00Z`)}</p>}
      {round && (
        <ol className="past">
          {round.questions.map((q) => {
            const res = round.results[q.id];
            const sky = !res ? w.pending : res.void ? w.void : res.yes ? w.yes : w.no;
            return (
              <li key={q.id}>
                <p className="oid">{q.object}</p>
                <p>{f.question(q.question)}</p>
                <dl>
                  <div><dt>{w.sira}</dt><dd>{f.pct(round.answers[q.id])}</dd></div>
                  {round.crowd && round.crowd[q.id] !== undefined && round.crowd[q.id] !== null && <div><dt>{w.crowd}</dt><dd>{f.pct(round.crowd[q.id])}</dd></div>}
                  <div><dt>{w.sky}</dt><dd className={res && res.void ? 'muted' : undefined}>{sky}</dd></div>
                </dl>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function Board({ beat, w, f }) {
  const players = beat.rounds.reduce((n, r) => Math.max(n, r.players || 0), 0);
  const rows = beat.board.length ? beat.board : ['sira', 'crowd', 'sira_crowd'].map((who) => ({ who, resolved: 0, mean: null }));
  return (
    <section aria-labelledby="board">
      <h2 id="board">{w.board}</h2>
      <p className="when">{w.players(players)}</p>
      <table className="board">
        <thead><tr><th>{w.who}</th><th className="n">{w.resolved}</th><th className="n">{w.mean}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.who} className={r.who === 'sira' ? 'us' : undefined}>
              <td>{w.rows[r.who] || r.handle || r.who}</td>
              <td className="n">{r.resolved}</td>
              <td className="n">{r.mean === null ? '—' : f.num(r.mean, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function Beat({ lang, live }) {
  const w = WORDS[lang].beat;
  const f = format(lang);
  const [rows, setRows] = useState(supabase ? null : []);
  const [clock, setClock] = useState(Date.now);
  const [offline, setOffline] = useState(!supabase);
  const [values, setValues] = useState({});
  const [mine, setMine] = useState({});
  const [alias, setAlias] = useState('');
  const [status, setStatus] = useState('idle');
  const [bank, setBank] = useState(null);

  const loadMine = async (ids) => {
    const { data: session } = await supabase.auth.getSession();
    if (!session.session || !ids.length) return;
    const { data } = await supabase.from('bets').select('question_id,p_yes').in('question_id', ids);
    if (data) setMine(Object.fromEntries(data.map((b) => [b.question_id, Number(b.p_yes)])));
  };

  // every question not yet closed, so one about to open can count down and appear on time
  const load = () => {
    const now = new Date();
    supabase.from('questions').select('*').gt('closes_at', now.toISOString()).order('id').then(({ data, error }) => {
      if (error) { setOffline(true); setRows([]); return; }
      setClock(Date.now());
      setRows(data);
      loadMine(data.filter((q) => new Date(q.opens_at) <= now).map((q) => q.id));
    });
  };

  useEffect(() => {
    if (supabase) load();
    fetch(`${BASE}replays/practice.json`).then((r) => (r.ok ? r.json() : null)).then(setBank).catch(() => setBank(null));
  }, []);

  const questions = rows && rows.filter((q) => Date.parse(q.opens_at) <= clock);
  const soon = rows ? rows.filter((q) => Date.parse(q.opens_at) > clock).map((q) => Date.parse(q.opens_at)) : [];
  const next = soon.length ? Math.min(...soon) : null;
  const end = questions && questions.length ? Math.min(...questions.map((q) => Date.parse(q.closes_at))) : null;

  useEffect(() => {
    if (next === null) return undefined;
    const tick = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [next]);
  useEffect(() => {
    // ask again the moment a round opens or closes
    const at = [next, end].filter((t) => t !== null);
    if (!at.length) return undefined;
    const timer = setTimeout(load, Math.max(1000, Math.min(...at) - Date.now() + 1000));
    return () => clearTimeout(timer);
  }, [next, end]);

  const send = async () => {
    const handle = alias.trim();
    if (!ALIAS.test(handle)) { setStatus('alias'); return; }
    setStatus('sending');
    const { data: session } = await supabase.auth.getSession();
    if (!session.session) {
      const { error } = await supabase.auth.signInAnonymously();
      if (error) { setStatus('error'); return; }
    }
    const rows = questions.map((q) => ({ question_id: q.id, handle, p_yes: (values[q.id] || 50) / 100 }));
    const { error } = await supabase.from('bets').insert(rows);
    if (error) { setStatus(error.code === '23505' ? 'already' : 'error'); return; }
    setStatus('sent');
    loadMine(questions.map((q) => q.id));
  };

  const open = questions && questions.length > 0;
  const closes = open ? f.chile(questions[0].closes_at) : '18:00';
  const betted = open && questions.every((q) => mine[q.id] !== undefined);
  const notes = { alias: [w.aliasNote, 'bad'], error: [w.failed, 'bad'], already: [w.already, 'bad'], sent: [w.sentNote(closes), 'ok'] };
  const beat = live ? live.beat : { rounds: [], board: [] };
  const lastRound = beat.rounds.find((r) => Object.keys(r.answers).length);
  // a question's images come with the site's data: from its round once the site has it, else from last night's candidates
  const images = (q) => {
    const round = beat.rounds.find((r) => r.round === q.round);
    const asked = round && round.questions.find((x) => x.id === q.id);
    const seen = live && live.candidates.find((c) => c.object === q.object);
    return (asked && asked.images && asked.images.stamps ? asked.images : seen && seen.images) || null;
  };

  return (
    <div className="beat">
      <section aria-labelledby="today">
        <div className="head">
          <h1 id="today">{w.title}</h1>
          {open && <p className="state">{w.closes(closes)}</p>}
        </div>
        {questions === null && <p className="next">{WORDS[lang].loading}</p>}
        {questions !== null && !open && (
          <p className="next">
            {offline ? w.offline : next !== null ? w.opens(f.chile(new Date(next).toISOString())) : w.none}
            {next !== null && !offline && <> {w.opensIn} <b>{countdown(next - clock)}</b>.</>}
          </p>
        )}
        {open && questions.map((q, i) => (
          <Live key={q.id} q={q} i={i} img={images(q)} closes={closes} betted={betted} lang={lang} w={w} f={f}
            value={mine[q.id] !== undefined ? Math.round(mine[q.id] * 100) : values[q.id] || 50}
            set={(v) => setValues({ ...values, [q.id]: v })} />
        ))}
        {open && (
          <div className="seal">
            <label>
              <span>{w.alias}</span>
              <input type="text" value={alias} maxLength={24} disabled={betted} onChange={(e) => setAlias(e.target.value)} />
            </label>
            <button type="button" className="btn primary" disabled={betted || status === 'sending'} onClick={send}>
              {betted ? w.sent : status === 'sending' ? w.sending : w.send(questions.length)}
            </button>
            {notes[status] && <p className={`note ${notes[status][1]}`}>{notes[status][0]}</p>}
          </div>
        )}
      </section>

      {bank && bank.questions.length > 0 && <Practice bank={bank} lang={lang} w={w} f={f} />}

      <div className="trio">
        <LastRound round={lastRound} w={w} f={f} />
        <Board beat={beat} w={w} f={f} />
        <section aria-labelledby="rules">
          <h2 id="rules">{w.rules}</h2>
          <ol className="rules">{w.ruleList.map((r) => <li key={r}>{r}</li>)}</ol>
        </section>
      </div>
    </div>
  );
}
