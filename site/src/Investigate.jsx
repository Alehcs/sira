import { useEffect, useState } from 'react';
import { supabase } from './supabase.js';
import { WORDS, format } from './words.js';

const COLS = 'id,object,status,steps,result,error,cost_usd,created_at,started_at,finished_at';
const DAILY = 10; // the same cap the database keeps
const COLORS = { reader: '#5CE1E6', theorist: '#FF9F43', skeptic: '#C49BFF', llm_only: '#7B96FF', director: '#FFD447', senior: '#FF6AD5', forecaster: '#7CF29C', lab: '#FF7A7A' };
const LETTERS = { reader: 'L', theorist: 'T', skeptic: 'S', llm_only: 'M', director: 'D', senior: 'W', forecaster: 'F', lab: '!' };
const STAGES = ['reader', 'theorist', 'skeptic', 'llm_only', 'director', 'forecaster']; // what a full run reports, in order
const HUE = { ia: '#7B96FF', ibc: '#8A88B0', ii: '#D9A47C', tde: '#C49BFF', other: '#5C5A85', null: '#5C5A85', adopted: '#FF9F43' };
const MINE = 'investigation';

const startOfDay = () => `${new Date().toISOString().slice(0, 10)}T00:00:00Z`;
const remember = (id) => { try { localStorage.setItem(MINE, String(id)); } catch (e) { /* storage can be blocked */ } };
const recall = () => { try { return Number(localStorage.getItem(MINE)) || null; } catch (e) { return null; } };

function say(s, w, f, hyp) {
  const d = s.decision || '';
  if (s.error) return w.callFailed;
  if (s.role === 'reader') {
    const m = /^(real|bogus) \(([\d.]+)\)$/.exec(d);
    return m ? w.reads(m[1], f.pct(Number(m[2]))) : w.unread;
  }
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

function Steps({ steps, running, w, f, hyp }) {
  const done = new Set(steps.map((s) => s.role));
  const waiting = running ? STAGES.filter((r) => !done.has(r)) : [];
  return (
    <ol className="log">
      {steps.map((s, i) => (
        <li key={i}>
          <span className="mark" style={{ background: COLORS[s.role] || '#B8B4E0' }}>{LETTERS[s.role] || '?'}</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
            <div className="when">
              <span>{s.role === 'skeptic' ? w.skeptic(s.lens) : w.roles[s.role] || s.role}</span>
              {s.model && <span className="mono">{s.model.split('/').pop()}</span>}
              {typeof s.seconds === 'number' && <span>{f.num(s.seconds, 0)} s</span>}
            </div>
            <span style={{ fontSize: 16 }}>{say(s, w, f, hyp)}</span>
            {s.why && <q style={{ fontSize: 15, color: '#B8B4E0', overflowWrap: 'anywhere' }}>{s.why}</q>}
          </div>
        </li>
      ))}
      {waiting.map((r) => (
        <li key={r} className="old">
          <span className="mark" style={{ background: COLORS[r] }}>{LETTERS[r]}</span>
          <div className="when"><span>{r === 'skeptic' ? w.skeptics : w.roles[r]}</span><span>{w.thinking}</span></div>
        </li>
      ))}
    </ol>
  );
}

function Forecast({ result, oid, w }) {
  // the recent detections, the team's forecast for each band (mean and one sigma either side) and the question staked
  const q = result.question;
  const seen = (result.seen || []).filter((p) => p[0] >= -30 && p[2] > 0);
  const fan = result.fan || [];
  const values = seen.map((p) => p[2]).concat(fan.map((p) => p[2] + p[3]), fan.map((p) => p[2]).filter((v) => v > 0), q ? [q.reference] : []);
  if (!values.length) return null;
  const start = Math.min(-2, Math.floor(Math.min(0, ...seen.map((p) => p[0]))) - 2);
  const ahead = Math.max(1, ...fan.map((p) => p[0]));
  const lo = Math.log10(Math.max(5, Math.min(...values) / 1.6));
  const hi = Math.log10(Math.max(...values) * 1.6);
  const X = (d) => ((d - start) / (ahead + 0.5 - start)) * 520;
  const Y = (v) => 122 - ((Math.log10(Math.max(v, 10 ** lo)) - lo) / (hi - lo)) * 114;
  const squares = (band) => seen.filter((p) => p[1] === band).map((p) => `M${(X(p[0]) - 3).toFixed(0)} ${(Y(p[2]) - 3).toFixed(0)}h6v6h-6z`).join(' ');
  const cone = (band) => {
    const pts = fan.filter((p) => p[1] === band).sort((a, b) => a[0] - b[0]);
    if (!pts.length) return null;
    const at = (p, v) => `${X(p[0]).toFixed(1)},${Y(v).toFixed(1)}`;
    return {
      area: pts.map((p) => at(p, p[2] + p[3])).concat(pts.slice().reverse().map((p) => at(p, p[2] - p[3]))).join(' '),
      line: pts.map((p) => at(p, p[2])).join(' '),
    };
  };
  const g = cone('ztfg');
  const r = cone('ztfr');
  return (
    <svg viewBox="0 0 520 150" shapeRendering="crispEdges" role="img" aria-label={w.chart(oid)}>
      <rect x="0" y="0" width="520" height="130" fill="#0B0B1A" />
      {q && <rect x={X(q.days - 0.5)} y="0" width={X(q.days + 0.5) - X(q.days - 0.5)} height="130" fill="#FFD447" fillOpacity="0.12" />}
      {q && <text x={X(q.days)} y="22" textAnchor="middle" fill="#FFD447" fontSize="18">?</text>}
      {g && <polygon points={g.area} fill="#7CF29C" fillOpacity="0.14" />}
      {r && <polygon points={r.area} fill="#FF7A7A" fillOpacity="0.18" />}
      {g && <polyline points={g.line} fill="none" stroke="#7CF29C" strokeWidth="2" />}
      {r && <polyline points={r.line} fill="none" stroke="#FF7A7A" strokeWidth="2" />}
      {q && <line x1="0" y1={Y(q.reference)} x2="520" y2={Y(q.reference)} stroke="#FFD447" strokeWidth="2" strokeDasharray="6 6" />}
      <line x1={X(0)} y1="0" x2={X(0)} y2="130" stroke="#F2F0FF" strokeWidth="2" />
      <path d={squares('ztfg')} fill="#7CF29C" />
      <path d={squares('ztfr')} fill="#FF7A7A" />
      <text x="4" y="146" fill="#B8B4E0" fontSize="13">{w.daysAgo(-start)}</text>
      <text x={X(0)} y="146" textAnchor="middle" fill="#F2F0FF" fontSize="13">{w.now}</text>
      <text x="516" y="146" textAnchor="end" fill="#FFD447" fontSize="13">+{Math.round(ahead)} d</text>
    </svg>
  );
}

function Result({ inv, w, f, hyp }) {
  const r = inv.result;
  if (inv.status === 'failed') return <p className="note bad">{w.errors[inv.error] || w.errors.failed}</p>;
  if (!r) return null;
  if (r.dropped) return <p className="note bad">{w.dropped}</p>;
  const classes = Object.entries(r.classes || {}).filter(([, v]) => v >= 0.02).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <article className="question">
        <div className="row">
          <h3 className="pixel" style={{ margin: 0, fontSize: 16, color: '#FFD447' }}>{w.bet}</h3>
          <span className="arcade" style={{ fontSize: 20, color: '#FFD447' }}>{f.pct(r.question.p)}</span>
        </div>
        <p>{f.question(r.question)}</p>
        <p className="muted" style={{ margin: 0 }}>{f.term(r.term)}</p>
        <Forecast result={r} oid={inv.object} w={w} />
      </article>
      <section className="panel" aria-label={w.classes}>
        <h2>{w.classes}</h2>
        {classes.map(([k, v]) => (
          <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div className="row" style={{ fontSize: 15 }}><span>{hyp[k] || k}</span><span>{f.pct(v)}</span></div>
            <div className="bar"><div style={{ width: `${Math.round(v * 100)}%`, background: HUE[k] || '#5C5A85' }} /></div>
          </div>
        ))}
      </section>
    </>
  );
}

function Watch({ inv, w, f, hyp, onBack }) {
  if (!inv) return <p className="muted">…</p>;
  const running = inv.status === 'queued' || inv.status === 'running';
  const end = inv.finished_at ? new Date(inv.finished_at) : new Date();
  const secs = Math.max(0, Math.round((end - new Date(inv.created_at)) / 1000));
  return (
    <>
      <div className="row">
        <span className="mono" style={{ fontSize: 16 }}>{inv.object}</span>
        <span className="pixel" style={{ fontSize: 15, color: running ? '#5CE1E6' : inv.status === 'done' ? '#7CF29C' : '#FF7A7A' }}>{w.status[inv.status]}</span>
        <span className="muted" style={{ fontSize: 14 }}>{`${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`}</span>
        <span className="muted" style={{ fontSize: 14 }}>{f.money(Number(inv.cost_usd) || 0)}</span>
      </div>
      {inv.status === 'queued' && secs > 180 && <p className="note bad">{w.errors.stale}</p>}
      <Steps steps={inv.steps || []} running={inv.status === 'running'} w={w} f={f} hyp={hyp} />
      <Result inv={inv} w={w} f={f} hyp={hyp} />
      <button type="button" className="button" style={{ alignSelf: 'flex-start' }} onClick={onBack}>{w.back}</button>
    </>
  );
}

function Candidates({ rows, held, blocked, starting, onPick, w, f }) {
  if (!rows.length) return null;
  return (
    <>
      <h3 className="pixel" style={{ margin: 0, fontSize: 16, color: '#5CE1E6' }}>{w.candidates}</h3>
      <div className="rooms">
        {rows.map((c) => (
          <article key={c.object} className="room">
            <div className="row">
              <span className="mono" style={{ fontSize: 15 }}>{c.object}</span>
              <a className="muted" style={{ fontSize: 13 }} href={`https://alerce.online/object/${c.object}`} target="_blank" rel="noreferrer">ALeRCE ↗</a>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              <span className="chip">{c.picked ? w.picked : w.passed}</span>
              {c.reader && <span className="chip">{w.reader(c.reader, f.pct(c.p_real))}</span>}
              {c.bet && <span className="chip on">{w.betLast}</span>}
              {held.has(c.object) && <span className="chip">{w.inRound}</span>}
            </div>
            <button type="button" className="button primary" disabled={blocked || held.has(c.object) || starting !== null}
              onClick={() => onPick(c.object)} style={{ minHeight: 44 }}>
              {starting === c.object ? w.starting : w.investigate}
            </button>
          </article>
        ))}
      </div>
    </>
  );
}

function Today({ rows, w, f, onOpen }) {
  if (!rows.length) return null;
  return (
    <section className="panel" aria-label={w.today}>
      <h2>{w.today}</h2>
      {rows.map((r) => (
        <button key={r.id} type="button" className="visit" onClick={() => onOpen(r.id)}>
          <span className="mono">{r.object}</span>
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
      if (mine && (mine.status === 'queued' || mine.status === 'running')) setWatching(mine.id);
    });
  }, []);

  useEffect(() => {
    if (!watching) return undefined;
    let alive = true;
    let timer;
    const tick = async () => {
      const { data } = await supabase.from('investigations').select(COLS).eq('id', watching).maybeSingle();
      if (!alive) return;
      if (data) setCurrent(data);
      if (!data || data.status === 'queued' || data.status === 'running') timer = setTimeout(tick, 3000);
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

  const now = new Date();
  const held = new Set((live ? live.beat.rounds : []).filter((r) => new Date(r.closes_at) > now).flatMap((r) => r.questions.map((q) => q.object)));
  const left = list ? Math.max(0, DAILY - list.length) : null;
  const busy = list ? list.some((r) => r.id === recall() && (r.status === 'queued' || r.status === 'running')) : false;

  return (
    <div className="cols">
      <section className="main" aria-label={w.title}>
        <div className="row">
          <h2 className="heading">{w.title}</h2>
          {!offline && left !== null && <span className="pixel" style={{ fontSize: 16, color: '#FFD447' }}>{w.left(left)}</span>}
        </div>
        {offline && <p className="note">{w.offline}</p>}
        {note && <p className="note bad">{w.refused[note]}</p>}
        {watching
          ? <Watch inv={current && current.id === watching ? current : null} w={w} f={f} hyp={hyp} onBack={() => { setWatching(null); setCurrent(null); }} />
          : <Candidates rows={live ? live.candidates || [] : []} held={held} blocked={offline || left === 0 || busy} starting={starting} onPick={start} w={w} f={f} />}
      </section>
      <aside className="side">
        <Today rows={list || []} w={w} f={f} onOpen={(id) => { setCurrent(null); setWatching(id); }} />
        <section className="panel">
          <button type="button" className="button" style={{ alignSelf: 'flex-start' }} aria-expanded={how} onClick={() => setHow(!how)}>{w.how}</button>
          {how && <ol style={{ margin: 0, paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 16, lineHeight: 1.4 }}>{w.howList.map((r) => <li key={r}>{r}</li>)}</ol>}
        </section>
      </aside>
    </div>
  );
}
