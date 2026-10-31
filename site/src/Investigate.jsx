import { useEffect, useState } from 'react';
import Figure from './ui/Figure.jsx';
import Paper from './ui/Paper.jsx';
import Stamps from './ui/Stamps.jsx';
import { Message, Thread } from './ui/Thread.jsx';
import { supabase } from './supabase.js';
import { WORDS, format } from './words.js';
import './investigate.css';

const BASE = import.meta.env.BASE_URL;
const COLS = 'id,object,status,steps,result,error,cost_usd,created_at,started_at,finished_at';
const DAILY = 10; // the same cap the database keeps
const SHOWN = 9;
const STAGES = ['reader', 'theorist', 'skeptic', 'llm_only', 'director', 'forecaster']; // what a full run reports, in order
const MINE = 'investigation';

const startOfDay = () => `${new Date().toISOString().slice(0, 10)}T00:00:00Z`;
const remember = (id) => { try { localStorage.setItem(MINE, String(id)); } catch (e) { /* storage can be blocked */ } };
const recall = () => { try { return Number(localStorage.getItem(MINE)) || null; } catch (e) { return null; } };
const mjdOf = (iso) => new Date(iso).getTime() / 86400000 + 40587;
const busy = (r) => r.status === 'queued' || r.status === 'running';

export const cost = (lang, f, v) => `US$${lang === 'es' ? ' ' : ''}${f.num(v, 3)}`;
export const model = (s) => (s.model ? `${s.model.split('/').pop()}${s.effort ? ` ${s.effort}` : ''}` : null);
export const who = (s, w) => (s.role === 'skeptic' ? w.skeptic(s.lens) : w.roles[s.role] || s.role);
export const flux = (f, v) => f.num(v, Number.isInteger(v) ? 0 : 1);
// the ledger cuts these notes at 200 characters: end on the last whole sentence, or show the cut
export const whole = (t) => {
  if (!t || t.length < 190 || /[.!?…]$/.test(t)) return t;
  const cut = t.lastIndexOf('. ');
  return cut > 0 ? t.slice(0, cut + 1) : `${t.trimEnd()}…`;
};

// one agent's step in a sentence of the site's own words
export function say(s, w, f, hyp) {
  const d = String(s.decision || '');
  if (s.error) return w.callFailed;
  if (s.role === 'reader') {
    const m = /^(real|bogus) \(([\d.]+)\)$/.exec(d);
    return m ? w.reads(m[1] === 'real', f.pct(Number(m[2]))) : w.unread;
  }
  if (s.role === 'lookout') return w.looks(d === 'investigate', f.num(s.priority || 0, 2));
  if (s.role === 'theorist') return w.defends(hyp[d.replace('defends ', '')] || d.replace('defends ', ''));
  if (s.role === 'skeptic' && s.lens === 'instrument') return d === 'artifact' ? w.artifact : w.realSource;
  if (s.role === 'skeptic' && s.lens === 'physics') return d.startsWith('doubts ') ? w.doubts(d.slice(7).split(', ').map((h) => hyp[h] || h)) : w.noObjection;
  if (s.role === 'skeptic') return d === 'recognises it' ? w.recognises : w.forgets;
  if (s.role === 'llm_only') return w.alone(Number((/\d+/.exec(d) || ['0'])[0]));
  if (s.role === 'director' || s.role === 'senior') return w.directs(d.split(' ')[0]);
  if (s.role === 'forecaster') return w.words;
  if (s.role === 'lab') return w.dropped;
  return d;
}

// the skeptics' own sentences, from their verdicts, for a step that came without words
export function heard(s, lenses, hyp) {
  if (s.role !== 'skeptic' || !lenses) return null;
  if (s.lens === 'instrument') return lenses.instrument && whole(lenses.instrument.why);
  if (s.lens === 'physics') return [].concat((lenses.physics && (lenses.physics.implausible || lenses.physics)) || []).map((i) => `${hyp[i.hypothesis] || i.hypothesis}: ${whole(i.why)}`).join(' ');
  return lenses.memory && lenses.memory.recognised ? lenses.memory.name : null;
}

export function Classes({ odds, hyp, f }) {
  const rows = Object.entries(odds).filter(([, v]) => v >= 0.005).sort((a, b) => (a[0] === 'null') - (b[0] === 'null') || b[1] - a[1]);
  return (
    <div className="voices">
      {rows.map(([h, v]) => (
        <div key={h} className={`v${h === 'null' ? ' null' : ''}`}>
          <span>{hyp[h] || h}</span>
          <i aria-hidden="true"><b style={{ width: `${(v * 100).toFixed(1)}%` }} /></i>
          <span className="pct">{f.pct(v)}</span>
        </div>
      ))}
    </div>
  );
}

function Reader({ c, w, f }) {
  const [a, b] = w.reader(c.reader === 'real');
  return <>{a}<b>{f.pct(c.p_real)}</b>{b}</>;
}

function Bet({ c, w, f }) {
  const t = c.telegram;
  return t ? w.bet(f.pct(t.question.p), f.term(t.term)) : w.noBet;
}

function Card({ c, on, ran, onPick, w, f }) {
  const im = c.images || {};
  const key = (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(c); }
  };
  return (
    <article className="card" role="radio" aria-checked={on} tabIndex={0} aria-label={c.object} onClick={() => onPick(c)} onKeyDown={key}>
      <div className="cin">
        <div className="ctext">
          <h3>{c.object}</h3>
          {c.reader && <p className="call"><Reader c={c} w={w} f={f} /></p>}
          <p>{c.bet ? <Bet c={c} w={w} f={f} /> : w.noBet}</p>
          {ran && <p>{w.ran(ran.result && ran.result.question ? f.pct(ran.result.question.p) : null)}</p>}
          {c.ra !== null && c.ra !== undefined && <p className="pos">{f.ra(c.ra)}<br />{f.dec(c.dec)}</p>}
        </div>
        {im.host && <img className="host" src={BASE + im.host} width="128" height="128" alt={w.hostAlt(c.object)} />}
        {im.stamps && <Stamps src={BASE + im.stamps} size={[im.panel[0] * 3, im.panel[1]]} tile={im.panel[0]} scale={2} labels={w.panels} alt={w.stampsAlt(c.object)} />}
      </div>
    </article>
  );
}

// what the run has seen: its own points once done, last night's curve while the team works
function seenOf(inv, cand) {
  const r = inv.result;
  if (r && r.seen) return r.seen.map(([day, band, v, err]) => ({ day, band: band.slice(-1), flux: v, err }));
  if (!cand || !cand.curve) return [];
  const t0 = mjdOf(inv.started_at || inv.created_at);
  return cand.curve.filter((p) => p[2] === 'det' && p[3] > 0).map(([mjd, band, , v, err]) => ({ day: mjd - t0, band: band.slice(-1), flux: v, err }));
}

function Run({ inv, cand, lang, w, f, hyp, onBack }) {
  if (!inv) return <p className="muted">{WORDS[lang].loading}</p>;
  const r = inv.result || {};
  const steps = inv.steps || [];
  const done = new Set(steps.map((s) => s.role));
  const waiting = inv.status === 'running' ? STAGES.filter((s) => !done.has(s)) : [];
  const end = inv.finished_at ? new Date(inv.finished_at) : new Date();
  const secs = Math.max(0, Math.round((end - new Date(inv.created_at)) / 1000));
  const q = r.question;
  const points = seenOf(inv, cand).filter((p) => p.day >= -40);
  const fan = r.fan || [];
  const forecasts = ['ztfg', 'ztfr'].map((b) => ({ band: b.slice(-1), style: 'sealed', rows: fan.filter((p) => p[1] === b).sort((x, y) => x[0] - y[0]).map((p) => [p[0], p[2], p[3]]) }))
    .filter((fc) => fc.rows.length);
  const im = (cand && cand.images) || {};
  const quote = (s) => {
    if (lang === 'es' && s.why_es) return { text: s.why_es, lang: 'es' };
    const text = s.why || heard(s, r.skeptics, hyp);
    return text ? { text, lang: 'en' } : null;
  };
  const attach = (s) => {
    if (s.role === 'reader' && im.stamps) return <Stamps src={BASE + im.stamps} size={[im.panel[0] * 3, im.panel[1]]} tile={im.panel[0]} scale={2} labels={w.panels} alt={w.stampsAlt(inv.object)} />;
    if (s.role !== 'forecaster' || !q) return null;
    return (
      <div className="betbox">
        <Paper question={f.question(q)} p={f.pct(q.p)} term={f.term(r.term)} />
        {r.classes && <Classes odds={r.classes} hyp={hyp} f={f} />}
      </div>
    );
  };
  const last = steps.length - 1;
  const stale = inv.status === 'queued' && secs > 180;
  return (
    <>
      <div className="runhead">
        <h1>{inv.object}</h1>
        <span className={`st ${inv.status}`}>{w.status[inv.status]}</span>
        <span className="meta">{`${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`}</span>
        <span className="meta">{f.money(Number(inv.cost_usd) || 0)}</span>
        <button type="button" className="btn" onClick={onBack}>{w.back}</button>
      </div>
      {stale && <p className="alert bad">{w.errors.stale}</p>}
      {inv.status === 'failed' && <p className="alert bad">{w.errors[inv.error] || w.errors.failed}</p>}
      {r.dropped && <p className="alert bad">{w.dropped}</p>}
      <div className="run">
        <Thread lang={lang} label={w.thread} current={`${inv.id}:${steps.length}:${inv.status}`}>
          {steps.map((s, i) => (
            <Message key={i} mark={w.marks[s.role] || '?'} name={who(s, w)} model={model(s)}
              when={typeof s.seconds === 'number' ? `${f.num(s.seconds, 0)} s` : null} at={`PT${Math.round(s.seconds || 0)}S`}
              cost={s.cost_usd ? cost(lang, f, s.cost_usd) : null} text={say(s, w, f, hyp)} quote={quote(s)} current={i === last}>
              {attach(s)}
            </Message>
          ))}
          {waiting.map((s) => <Message key={s} mark={w.marks[s]} name={s === 'skeptic' ? w.skeptics : w.roles[s]} text={w.thinking} />)}
        </Thread>
        <section className="fig">
          {points.length > 0 && (
            <Figure lang={lang} start={inv.started_at || inv.created_at} points={points} forecasts={forecasts} now={0}
              reference={q ? { flux: q.reference, label: w.at(flux(f, q.reference), q.band) } : null}
              target={q ? { day: q.days, label: f.short(q.due) } : null} label={w.chart(inv.object)} />
          )}
        </section>
      </div>
    </>
  );
}

function Today({ rows, w, f, onOpen }) {
  if (!rows.length) return null;
  return (
    <section className="today" aria-label={w.today}>
      <h2>{w.today}</h2>
      {rows.map((r) => (
        <button key={r.id} type="button" onClick={() => onOpen(r.id)}>
          <span className="mono">{r.object}</span>
          <span className="muted">{f.chile(r.created_at)}</span>
          <span>{r.status === 'done' && r.result && r.result.question ? f.pct(r.result.question.p) : w.status[r.status]}</span>
        </button>
      ))}
    </section>
  );
}

export default function Investigate({ lang, live }) {
  const w = WORDS[lang].live;
  const hyp = { ...WORDS[lang].lab.hyp, other: w.other };
  const f = format(lang);
  const [list, setList] = useState(supabase ? null : []);
  const [offline, setOffline] = useState(!supabase);
  const [watching, setWatching] = useState(null);
  const [current, setCurrent] = useState(null);
  const [note, setNote] = useState(null);
  const [starting, setStarting] = useState(null);
  const [how, setHow] = useState(false);
  const [picked, setPicked] = useState(null);
  const [round, setRound] = useState(new Set());

  const load = () => supabase.from('investigations').select(COLS).gte('created_at', startOfDay()).order('id', { ascending: false })
    .then(({ data, error }) => {
      if (error) { setOffline(true); setList([]); return []; }
      setList(data);
      return data;
    });

  useEffect(() => {
    if (!supabase) return;
    load().then((rows) => {
      // a visitor who comes back finds their run still going
      const mine = rows.find((r) => r.id === recall());
      if (mine && busy(mine)) setWatching(mine.id);
    });
    // objects in a Beat SIRA round that has not closed wait for the bell
    supabase.from('questions').select('object').gt('closes_at', new Date().toISOString())
      .then(({ data }) => setRound(new Set((data || []).map((q) => q.object))));
  }, []);

  useEffect(() => {
    if (!watching) return undefined;
    let alive = true;
    let timer;
    const tick = async () => {
      const { data } = await supabase.from('investigations').select(COLS).eq('id', watching).maybeSingle();
      if (!alive) return;
      if (data) setCurrent(data);
      if (!data || busy(data)) timer = setTimeout(tick, 3000);
      else load();
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [watching]);

  const start = async (oid) => {
    setStarting(oid);
    setNote(null);
    const { data: session } = await supabase.auth.getSession();
    if (!session.session) {
      const { error } = await supabase.auth.signInAnonymously();
      if (error) { setStarting(null); setNote('sign_in'); return; }
    }
    const { data, error } = await supabase.rpc('investigate', { target: oid });
    setStarting(null);
    if (error) { setNote(w.refused[error.message] ? error.message : 'error'); return; }
    remember(data);
    setCurrent(null);
    setWatching(data);
    load();
  };
  const open = (id) => { setCurrent(null); setWatching(id); };

  const now = new Date();
  const held = new Set([...round, ...(live ? live.beat.rounds : []).filter((r) => new Date(r.closes_at) > now).flatMap((r) => r.questions.map((q) => q.object))]);
  const all = live ? live.candidates || [] : [];
  const ok = all.filter((c) => (c.points || 0) >= (live.min_points || 0) && !held.has(c.object));
  const byPriority = (a, b) => b.priority - a.priority;
  const cards = ok.filter((c) => c.bet).sort(byPriority).concat(ok.filter((c) => !c.bet && c.reader === 'real').sort(byPriority)).slice(0, SHOWN);
  // the latest run of each object today, so a second visitor opens it instead of paying for another
  const ran = new Map();
  (list || []).filter((r) => r.status !== 'failed').forEach((r) => { if (!ran.has(r.object)) ran.set(r.object, r); });
  const left = list ? Math.max(0, DAILY - list.length) : null;
  const mine = (list || []).some((r) => r.id === recall() && busy(r));
  const sel = cards.find((c) => c.object === picked) || cards[0];
  const pick = (c) => (ran.has(c.object) ? open(ran.get(c.object).id) : setPicked(c.object));
  const watched = current && current.id === watching ? current : null;

  const below = (
    <div className="below">
      <Today rows={list || []} w={w} f={f} onOpen={open} />
      <section className="how">
        <button type="button" className="btn" aria-expanded={how} onClick={() => setHow(!how)}>{w.how}</button>
        {how && <ol>{w.howList.map((r) => <li key={r}>{r}</li>)}</ol>}
      </section>
    </div>
  );

  if (watching) {
    return (
      <>
        <Run inv={watched} cand={watched && all.find((c) => c.object === watched.object)} lang={lang} w={w} f={f} hyp={hyp}
          onBack={() => { setWatching(null); setCurrent(null); }} />
        {below}
      </>
    );
  }
  const head = live && live.head;
  return (
    <>
      <div className="invhead">
        <h1>{w.title}</h1>
        {head && head.tsa_time && <p>{w.sealed(f.stamp(head.tsa_time), head.hash.slice(0, 8))}</p>}
      </div>
      <h2 className="subhead">{w.candidates}</h2>
      {offline && <p className="alert">{w.offline}</p>}
      {note && <p className="alert bad">{w.refused[note]}</p>}
      {!live && <p className="muted">{WORDS[lang].loading}</p>}
      {live && !cards.length && <p className="muted">{w.none}</p>}
      {sel && (
        <div className="pick">
          <span className="oid">{sel.object}</span>
          {sel.reader && <span className="fact"><Reader c={sel} w={w} f={f} /></span>}
          <span className="fact">{sel.bet ? <Bet c={sel} w={w} f={f} /> : w.noBet}</span>
          <a className="fact" href={`https://alerce.online/object/${sel.object}`} target="_blank" rel="noreferrer">ALeRCE</a>
          <span className="go">
            {!offline && left !== null && <span className="left">{w.left[0]} <b>{left}</b> {w.left[1]}</span>}
            {ran.has(sel.object)
              ? <button type="button" className="btn primary tall" onClick={() => open(ran.get(sel.object).id)}>{w.open}</button>
              : (
                <button type="button" className="btn primary tall" disabled={offline || left === 0 || mine || starting !== null} onClick={() => start(sel.object)}>
                  {starting === sel.object ? w.starting : w.investigate}
                </button>
              )}
          </span>
        </div>
      )}
      {cards.length > 0 && (
        <div className="cards" role="radiogroup" aria-label={w.candidates}>
          {cards.map((c) => <Card key={c.object} c={c} on={c === sel} ran={ran.get(c.object)} onPick={pick} w={w} f={f} />)}
        </div>
      )}
      {below}
    </>
  );
}
