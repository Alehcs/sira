// a sealed record: the question and its percentage, or a verdict, then the seal and the sky's answer
export default function Paper({ title, tone, question, p, term, children, hash, time, answer }) {
  return (
    <div className="paper">
      {title && <p className={`title${tone ? ` ${tone}` : ''}`}>{title}</p>}
      {question && <p className="q">{question}</p>}
      {p && <div className="p"><b>{p}</b>{term && <span>{term}</span>}</div>}
      {children}
      {(hash || time) && (
        <div className="meta">
          {hash && <span>sha256&nbsp;{hash}…</span>}
          {time && <span>{time}</span>}
        </div>
      )}
      {answer && <div className={`answer${answer.tone ? ` ${answer.tone}` : ''}`}>{answer.text}{answer.detail && <span>{answer.detail}</span>}</div>}
    </div>
  );
}
