import { useEffect, useState } from 'react';
import { Envelope } from './pixel.jsx';
import { supabase } from './supabase.js';
import { WORDS, format } from './words.js';

const LEVEL = /^(Brighter|Fainter) than ([\d.]+) microjansky in (\w) (\d+) days from now\?$/;
const toMjd = (iso) => new Date(iso).getTime() / 86400000 + 40587;

function fields(q) {
  const m = LEVEL.exec(q.text);
  if (m) return { kind: 'level', direction: m[1] === 'Brighter' ? 'above' : 'below', reference: Number(m[2]), band: m[3], days: Number(m[4]) };
  return { kind: 'last', direction: 'above', reference: Math.round(q.reference * 10) / 10, band: (q.band || 'ztfr').slice(-1), days: 3 };
}

function Curve({ q, w, label }) {
  // days before the round opened on x, flux on a log scale on y, the bet's window shaded
  const now = toMjd(q.opens_at);
  const ahead = q.mjd - now;
  const dets = (q.seen || []).filter((p) => p[2] === 'det' && p[3] > 0 && now - p[0] <= 30);
  const fluxes = dets.map((p) => p[3]).concat([q.reference]);
  const lo = Math.log10(Math.max(5, Math.min(...fluxes) / 1.6));
  const hi = Math.log10(Math.max(...fluxes) * 1.6);
  const X = (d) => ((d + 30) / (30 + ahead + 1)) * 520;
  const Y = (f) => 122 - ((Math.log10(f) - lo) / (hi - lo)) * 114;
  const squares = (band) => dets.filter((p) => p[1] === band).map((p) => `M${(X(p[0] - now) - 3).toFixed(0)} ${(Y(p[3]) - 3).toFixed(0)}h6v6h-6z`).join(' ');
  return (
    <svg viewBox="0 0 520 150" shapeRendering="crispEdges" role="img" aria-label={label}>
      <rect x="0" y="0" width="520" height="130" fill="#0B0B1A" />
      <rect x={X(ahead - 0.5)} y="0" width={X(ahead + 0.5) - X(ahead - 0.5)} height="130" fill="#FFD447" fillOpacity="0.12" />
      <text x={X(ahead)} y="70" textAnchor="middle" fill="#FFD447" fontSize="22">?</text>
      <line x1="0" y1={Y(q.reference)} x2="520" y2={Y(q.reference)} stroke="#FF7A7A" strokeWidth="2" strokeDasharray="6 6" />
      <line x1={X(0)} y1="0" x2={X(0)} y2="130" stroke="#F2F0FF" strokeWidth="2" />
      <path d={squares('ztfg')} fill="#7CF29C" />
      <path d={squares('ztfr')} fill="#FF7A7A" />
      <text x="4" y="146" fill="#B8B4E0" fontSize="13">{w.daysAgo(30)}</text>
      <text x={X(0)} y="146" textAnchor="middle" fill="#F2F0FF" fontSize="13">{w.today}</text>
      <text x="516" y="146" textAnchor="end" fill="#FFD447" fontSize="13">+{Math.round(ahead)} d</text>
    </svg>
  );
}

function Board({ live, w, f }) {
  const beat = live ? live.beat : { rounds: [], board: [] };
  const players = beat.rounds.reduce((n, r) => Math.max(n, r.players || 0), 0);
  const rows = beat.board.length ? beat.board : ['sira', 'crowd', 'sira_crowd'].map((who) => ({ who, resolved: 0, mean: null }));
  return (
    <section className="panel" aria-label={w.board}>
      <div className="row"><h2>{w.board}</h2><span className="muted" style={{ fontSize: 14 }}>{w.players(players)}</span></div>
      <table className="board">
        <thead><tr><th>{w.who}</th><th className="n">{w.resolved}</th><th className="n">{w.score}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.who}>
              <td style={{ color: r.who === 'sira' ? '#FFD447' : undefined }}>{w.rows[r.who] || r.handle || r.who}</td>
              <td className="n">{r.resolved}</td>
              <td className="n">{r.mean === null ? '—' : f.num(r.mean, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function LastRound({ round, w, f }) {
  if (!round || !Object.keys(round.answers).length) return null;
  return (
    <section className="panel" aria-label={w.last}>
      <div className="row"><h2>{w.last}</h2><span className="muted" style={{ fontSize: 14 }}>{f.day(`${round.round}T12:00:00Z`)}</span></div>
      {round.questions.map((q) => {
        const res = round.results[q.id];
        return (
          <div key={q.id} style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 10, borderTop: '2px solid #2A2850' }}>
            <span className="mono" style={{ fontSize: 14 }}>{q.object}</span>
            <span style={{ fontSize: 15 }}>{w.siraSaid} {f.pct(round.answers[q.id])}{round.crowd && round.crowd[q.id] !== undefined ? `, ${w.crowdSaid} ${f.pct(round.crowd[q.id])}` : ''}</span>
            <span className="muted" style={{ fontSize: 15 }}>{w.skyAnswer}: {res ? (res.yes ? w.yes : w.no) : w.pending}</span>
          </div>
        );
      })}
    </section>
  );
}

export default function Beat({ lang, live }) {
  const w = WORDS[lang].beat;
  const f = format(lang);
  const [questions, setQuestions] = useState(supabase ? null : []);
  const [offline, setOffline] = useState(!supabase);
  const [values, setValues] = useState({});
  const [mine, setMine] = useState({});
  const [alias, setAlias] = useState('');
  const [status, setStatus] = useState('idle');
  const [rules, setRules] = useState(false);

  const loadMine = async (ids) => {
    const { data: session } = await supabase.auth.getSession();
    if (!session.session || !ids.length) return;
    const { data } = await supabase.from('bets').select('question_id,p_yes').in('question_id', ids);
    if (data) setMine(Object.fromEntries(data.map((b) => [b.question_id, Number(b.p_yes)])));
  };

  useEffect(() => {
    if (!supabase) return;
    const now = new Date().toISOString();
    supabase.from('questions').select('*').lte('opens_at', now).gt('closes_at', now).order('id').then(({ data, error }) => {
      if (error) { setOffline(true); setQuestions([]); return; }
      setQuestions(data);
      loadMine(data.map((q) => q.id));
    });
  }, []);

  const send = async () => {
    const handle = alias.trim();
    if (handle.length < 2 || handle.length > 24) { setStatus('alias'); return; }
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
  const lastRound = live && live.beat.rounds.find((r) => Object.keys(r.answers).length);

  return (
    <div className="cols">
      <section className="main" aria-label={w.title}>
        <div className="row">
          <h2 className="heading">{w.title}</h2>
          {open && <span className="pixel" style={{ fontSize: 16, color: '#FFD447' }}>{w.closes(closes)}</span>}
        </div>
        {questions === null && <p className="muted">…</p>}
        {questions !== null && !open && <p className="note">{offline ? w.offline : w.none}</p>}
        {open && questions.map((q, i) => {
          const value = mine[q.id] !== undefined ? Math.round(mine[q.id] * 100) : values[q.id] || 50;
          return (
            <article key={q.id} className="question">
              <div className="row">
                <h3 className="pixel" style={{ margin: 0, fontSize: 16, color: '#FFD447' }}>{w.q} {i + 1}</h3>
                <span className="mono muted" style={{ fontSize: 14 }}>{q.object}</span>
              </div>
              <p>{f.question(fields(q))}</p>
              <div className="split">
                <Curve q={q} w={w} label={q.object} />
                <div className="pick">
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span className="muted" style={{ fontSize: 14 }}>{w.you}</span>
                    <span className="arcade" style={{ fontSize: 20, color: '#FFD447' }}>{f.pct(value / 100)}</span>
                    <input type="range" min="1" max="99" value={value} disabled={betted}
                      onChange={(e) => setValues({ ...values, [q.id]: Number(e.target.value) })} />
                  </label>
                  <div className="row muted" style={{ fontSize: 13 }}><span>{w.no}</span><span>{w.yes}</span></div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Envelope />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span className="muted" style={{ fontSize: 14 }}>{w.sira}</span>
                      <span style={{ fontSize: 15, color: '#FF6AD5' }}>{w.sealed(closes)}</span>
                      <span className="mono muted" style={{ fontSize: 12 }}>{q.commit.slice(0, 12)}…</span>
                    </div>
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </section>

      <aside className="side">
        {open && (
          <section className="panel">
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span className="pixel" style={{ fontSize: 15, color: '#5CE1E6' }}>{w.alias}</span>
              <input type="text" value={alias} maxLength={24} disabled={betted} onChange={(e) => setAlias(e.target.value)} />
            </label>
            <button type="button" className={`button ${betted || status === 'sent' ? 'done' : 'primary'}`} disabled={betted || status === 'sending'}
              onClick={send} style={{ minHeight: 48 }}>
              {betted ? w.sent : status === 'sending' ? w.sending : w.send(questions.length)}
            </button>
            {notes[status] && <span className={`note ${notes[status][1]}`}>{notes[status][0]}</span>}
          </section>
        )}
        <LastRound round={lastRound} w={w} f={f} />
        <Board live={live} w={w} f={f} />
        <section className="panel">
          <button type="button" className="button" style={{ alignSelf: 'flex-start' }} aria-expanded={rules} onClick={() => setRules(!rules)}>{w.rules}</button>
          {rules && <ol style={{ margin: 0, paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 16, lineHeight: 1.4 }}>{w.ruleList.map((r) => <li key={r}>{r}</li>)}</ol>}
        </section>
      </aside>
    </div>
  );
}
