import { useWidth } from './width.js';

const CHAR = 7.4;

// the replay as one bar, like a video's: a piece per step as long as it plays, the playing piece filling as it goes
export default function Timeline({ step, playing, pace, parts, marks, go, label, stepWord }) {
  const [root, width] = useWidth();
  const finite = pace.filter(Number.isFinite);
  const secs = pace.map((p) => (Number.isFinite(p) ? p : Math.max(1, ...finite)));
  const total = secs.reduce((a, b) => a + b, 0);
  const starts = secs.map((_, i) => secs.slice(0, i).reduce((a, b) => a + b, 0) / total);

  // a mark under the bar where its step starts, dropped when it would run into the one before
  let room = -Infinity;
  const shown = [];
  for (const m of marks) {
    const w = m.text.length * CHAR;
    const left = Math.min(Math.max(starts[m.i] * width, 0), Math.max(0, width - w));
    if (left < room + 12) continue;
    room = left + w;
    shown.push({ ...m, left });
  }

  return (
    <div className="timeline" ref={root} role="group" aria-label={label}>
      <div className="track">
        {parts.map((name, i) => (
          <button key={i} type="button" style={{ flexGrow: secs[i] }} className={i < step ? 'past' : undefined}
            aria-current={i === step ? 'step' : undefined} aria-label={`${stepWord} ${i + 1}: ${name}`} title={name} onClick={() => go(i)}>
            {i === step && <i key={`${step}${playing}`} className={playing ? 'filling' : undefined} style={playing ? { animationDuration: `${secs[i]}s` } : undefined} />}
          </button>
        ))}
      </div>
      {width > 0 && (
        <div className="marks" aria-hidden="true">
          {shown.map((m) => <span key={m.i} style={{ left: m.left }}>{m.text}</span>)}
        </div>
      )}
    </div>
  );
}
