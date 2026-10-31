import { useState } from 'react';
import Paper from './ui/Paper.jsx';
import { WORDS, format } from './words.js';

const RECIPE = 'git clone https://github.com/Alehcs/sira && cd sira\ngit worktree add ledger origin/ledger\nuv run sira verify --ledger ledger --online';

function Telegram({ t, w, f }) {
  const a = t.answer;
  let answer = { text: w.waiting, detail: w.due(f.day(t.answer_due)) };
  if (a && a.void) answer = { text: w.void, detail: w.voidWhy };
  else if (a) answer = { text: w.answer(a.yes), detail: `${w.score} ${f.num(a.log_score, 2)}`, tone: (t.question.p >= 0.5) === a.yes ? 'ok' : 'warn' };
  return (
    <article className="card">
      <p className="by"><b>{t.object}</b><span>{w.tg} {String(t.seq).padStart(4, '0')}</span><span>{w.models[t.model] || t.model}</span></p>
      <Paper question={f.question(t.question)} p={f.pct(t.question.p)} term={f.term(t.term)} hash={t.hash.slice(0, 12)}
        time={f.stamp(t.sealed_at || t.made_at)} answer={answer} />
    </article>
  );
}

export default function Telegrams({ lang, live }) {
  const [all, setAll] = useState(false);
  const [copied, setCopied] = useState(false);
  const w = WORDS[lang].tele;
  const f = format(lang);
  const r = live.record;
  const shown = all ? live.telegrams : live.telegrams.slice(0, 6);
  const copy = async () => {
    try { await navigator.clipboard.writeText(RECIPE); setCopied(true); } catch (e) { setCopied(false); }
  };
  return (
    <div className="tele">
      <section className="feed" aria-labelledby="forecasts">
        <div className="head"><h1 id="forecasts">{w.title}</h1><p className="state">{w.count(r.sealed)}</p></div>
        <div className="cards">{shown.map((t) => <Telegram key={t.seq} t={t} w={w} f={f} />)}</div>
        {live.telegrams.length > 6 && (
          <button type="button" className="btn" aria-expanded={all} onClick={() => setAll(!all)}>
            {all ? w.less : w.more(live.telegrams.length)}
          </button>
        )}
      </section>

      <aside>
        <section aria-labelledby="record">
          <h2 id="record">{w.record}</h2>
          <p className="big"><b>{r.answered}</b> / {r.sealed}</p>
          <p className="muted">{w.answered}</p>
          <ul>
            {r.answered > 0 && <li>{w.right(r.right, r.answered)}</li>}
            {r.void > 0 && <li>{w.voids(r.void)}</li>}
            <li>{w.scored(r.outcomes)}</li>
            {r.next_due && <li>{w.due2(f.day(r.next_due))}</li>}
          </ul>
        </section>

        {r.paired > 0 && (
          <section aria-labelledby="rivals">
            <h2 id="rivals">{w.rivals}</h2>
            <p className="muted">{w.rivalsN(r.paired)}</p>
            <table className="board">
              <tbody>
                {['sira', 'b0', 'b1', 'b2'].map((k) => (
                  <tr key={k} className={k === 'sira' ? 'us' : undefined}><td>{w.rivalNames[k]}</td><td className="n">{f.num(r.log_score[k], 2)}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <section aria-labelledby="seal">
          <h2 id="seal">{w.seal}</h2>
          <dl className="facts">
            <dt>FreeTSA</dt><dd>{live.head.tsa_time ? f.stamp(live.head.tsa_time) : ''}</dd>
            <dt>{w.head}</dt><dd>{(live.head.hash || '').slice(0, 16)}…</dd>
            {live.head.run && <><dt>{w.run}</dt><dd><a href={live.head.run}>{live.head.run.split('/').pop()}</a></dd></>}
          </dl>
        </section>

        <section aria-labelledby="check">
          <div className="row">
            <h2 id="check">{w.check}</h2>
            <button type="button" className="btn" onClick={copy}>{copied ? w.copied : w.copy}</button>
          </div>
          <pre className="recipe">{RECIPE}</pre>
        </section>
      </aside>
    </div>
  );
}
