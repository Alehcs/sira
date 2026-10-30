import { useState } from 'react';
import { WORDS, format } from './words.js';

const RECIPE = 'git clone https://github.com/Alehcs/sira && cd sira\ngit worktree add ledger origin/ledger\nuv run sira verify --ledger ledger --online';

function Telegram({ t, w, f }) {
  const a = t.answer;
  const said = t.term ? `${f.pct(t.question.p)} (${f.term(t.term)})` : f.pct(t.question.p);
  let answer = <dd className="pending">{w.waiting(f.day(t.question.due))}</dd>;
  if (a && a.void) answer = <dd>{w.void}</dd>;
  else if (a) {
    const right = (t.question.p >= 0.5) === a.yes;
    answer = <dd className={right ? 'right' : 'wrong'}>{a.yes ? w.yes : w.no}. {w.score} {f.num(a.log_score, 2)}. {f.stamp(a.at)}</dd>;
  }
  return (
    <article className="telegram">
      <header><strong>{w.tg} {String(t.seq).padStart(4, '0')}</strong><span>{f.stamp(t.made_at)}</span></header>
      <dl>
        <dt>{w.object}</dt><dd>{t.object}</dd>
        <dt>{w.model}</dt><dd>{w.models[t.model] || t.model}</dd>
        <dt>{w.question}</dt><dd>{f.question(t.question)}</dd>
        <dt>SIRA</dt><dd style={{ fontWeight: 700 }}>{said}</dd>
        <dt>{w.seal}</dt><dd>{t.hash.slice(0, 12)}… RFC 3161 {t.sealed_at ? f.stamp(t.sealed_at) : ''}</dd>
        <dt>{w.answer}</dt>{answer}
      </dl>
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
    <div className="cols">
      <section className="main" aria-label={w.title}>
        <div className="row"><h2 className="heading">{w.title}</h2><span className="muted">{w.count(r.sealed)}</span></div>
        {shown.map((t) => <Telegram key={t.seq} t={t} w={w} f={f} />)}
        {live.telegrams.length > 6 && (
          <button type="button" className="button" style={{ alignSelf: 'flex-start' }} aria-expanded={all} onClick={() => setAll(!all)}>
            {all ? w.less : w.more(live.telegrams.length)}
          </button>
        )}
      </section>

      <aside className="side">
        <section className="panel" aria-label={w.record}>
          <h2>{w.record}</h2>
          <span className="big">{r.answered} / {r.sealed}</span>
          <span className="muted">{w.answered}</span>
          {r.answered > 0 && <span>{w.right(r.right, r.answered)}</span>}
          <span>{w.scored(r.outcomes)}</span>
          {r.next_due && <span>{w.due(f.day(r.next_due))}</span>}
        </section>

        {r.paired > 0 && (
          <section className="panel" aria-label={w.rivals}>
            <h2>{w.rivals}</h2>
            <span className="muted">{w.rivalsN(r.paired)}</span>
            <table className="board">
              <tbody>
                {['sira', 'b0', 'b1', 'b2'].map((k) => (
                  <tr key={k}><td style={{ color: k === 'sira' ? '#FFD447' : undefined }}>{w.rivalNames[k]}</td><td className="n">{f.num(r.log_score[k], 2)}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <section className="panel" aria-label={w.seal2}>
          <h2>{w.seal2}</h2>
          <dl className="facts">
            <dt>FreeTSA</dt><dd className="mono">{live.head.tsa_time ? f.stamp(live.head.tsa_time) : ''}</dd>
            <dt>{w.head}</dt><dd className="mono">{(live.head.hash || '').slice(0, 16)}…</dd>
            {live.head.run && <><dt>{w.run}</dt><dd className="mono"><a href={live.head.run}>{live.head.run.split('/').pop()}</a></dd></>}
          </dl>
        </section>

        <section className="panel" aria-label={w.check}>
          <div className="row" style={{ alignItems: 'center' }}>
            <h2>{w.check}</h2>
            <button type="button" className={`button ${copied ? 'done' : 'primary'}`} onClick={copy}>{copied ? w.copied : w.copy}</button>
          </div>
          <pre className="recipe mono">{RECIPE}</pre>
        </section>
      </aside>
    </div>
  );
}
