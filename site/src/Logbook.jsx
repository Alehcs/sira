import { useState } from 'react';
import { WORDS, format } from './words.js';

const TONE = { neptune: 'good', adopted: 'good', vulcan: 'bad' };
const E = <span className="mono">log<sub>10</sub>{' '}<i className="v">E</i></span>;

function power(p, f) {
  const e = Math.floor(Math.log10(p));
  return <span className="mono"><i className="v">p</i> = {f.num(p / 10 ** e, 2)} × 10<sup>{String(e).replace('-', '−')}</sup></span>;
}

// a name and an idea in Spanish when the site is and Le Verrier's words have been translated, else in English
function spoken(lang, f, p) {
  const es = lang === 'es';
  const name = (es && p.name_es) || f.name(p.name);
  return {
    name, nameLang: name === p.name ? 'en' : 'es',
    idea: (es && p.idea_es) || p.idea, ideaLang: es && p.idea_es ? 'es' : 'en',
  };
}

function Node({ kind, w, lines, pick, pressed, wide }) {
  const inner = (
    <>
      <span className="kind">{w[kind]}</span>
      {lines.map((l, i) => <span key={i} className={l.dim ? 'dim' : undefined} lang={l.lang}>{l.text}</span>)}
    </>
  );
  const cls = `node${TONE[kind] ? ` ${TONE[kind]}` : ''}${wide ? ' wide' : ''}`;
  if (pick) return <button type="button" className={cls} aria-pressed={pressed} onClick={pick}>{inner}</button>;
  return <div className={cls}>{inner}</div>;
}

function nodesOf(chain, lane, key, lang, w, f, selected, choose) {
  const out = [
    { kind: 'surprise', lines: [{ text: f.day(chain.at), dim: true }, { text: w.outOf(chain.misses, chain.n) }, { text: power(chain.p, f), dim: true }] },
    {
      kind: 'proposals', key,
      lines: chain.proposals.map((p) => {
        const s = spoken(lang, f, p);
        return { text: s.name, lang: s.nameLang, dim: chain.verdict && !p.chosen };
      }).concat([{ text: <span className="mono">{f.money(chain.cost_usd)}</span>, dim: true }]),
    },
  ];
  if (chain.verdict) {
    const v = chain.verdict;
    out.push({ kind: v.verdict, lines: [{ text: <>{E} {f.num(v.log10_e, v.verdict === 'abstain' ? 2 : 1)}</> }, { text: w.points(v.n), dim: true }] });
    if (lane.adopted && v.verdict === 'neptune') out.push({ kind: 'adopted', lines: [{ text: w.joins }] });
  } else {
    const best = chain.proposals.filter((p) => p.verdict === 'neptune').sort((a, b) => b.log10_e - a.log10_e)[0];
    if (best) {
      const s = spoken(lang, f, best);
      out.push({ kind: 'neptune', lines: [{ text: s.name, lang: s.nameLang }, { text: <>{E} {f.num(best.log10_e)}</> }, { text: w.points(best.n), dim: true }] });
    }
    chain.proposals.filter((p) => p.verdict === 'vulcan').forEach((p) => {
      const s = spoken(lang, f, p);
      out.push({ kind: 'vulcan', lines: [{ text: s.name, lang: s.nameLang }, { text: <>{E} {f.num(p.log10_e)}</> }, { text: w.toGrave, dim: true }] });
    });
  }
  return out.map((n) => (n.key ? { ...n, pick: () => choose(n.key), pressed: selected === n.key } : n));
}

export default function Logbook({ lang, lanes, live }) {
  const w = WORDS[lang].log;
  const f = format(lang);
  const [selected, setSelected] = useState(`${lanes[0].object}:0`);
  const active = lanes.filter((l) => l.chains.length);
  const quiet = lanes.filter((l) => !l.chains.length);
  const rec = live ? live.record : { sealed: 0, answered: 0 };
  const liveChains = live ? live.surprises : [];

  const rows = [];
  const chains = {};
  active.forEach((lane) => lane.chains.forEach((chain, ci) => {
    chains[`${lane.object}:${ci}`] = chain;
    rows.push({
      key: `${lane.object}-${ci}`, who: ci === 0 ? lane.object : '', source: ci === 0 ? (lane.source === 'team' ? w.team : w.solo) : '',
      nodes: nodesOf(chain, lane, `${lane.object}:${ci}`, lang, w, f, selected, setSelected),
    });
  }));
  if (quiet.length) rows.push({ key: 'controls', who: quiet.map((l) => l.object).join(' '), source: w.controls, nodes: [{ kind: 'quiet', wide: true, lines: [{ text: w.quietText }] }] });
  liveChains.forEach((s, i) => {
    const chain = {
      at: s.at, misses: s.misses, n: s.n, p: s.p, cost_usd: s.leap ? s.leap.cost_usd : 0, verdict: s.verdict,
      proposals: s.leap ? s.leap.proposals.map((p) => ({ ...p, chosen: p.name === s.leap.chosen })) : [],
    };
    chains[`${s.object}:live${i}`] = chain;
    rows.push({ key: `live-${i}`, who: s.object, source: w.live, nodes: nodesOf(chain, { object: s.object }, `${s.object}:live${i}`, lang, w, f, selected, setSelected) });
  });
  if (!liveChains.length) rows.push({ key: 'live', who: 'SIRA', source: w.live, nodes: [{ kind: 'quiet', wide: true, lines: [{ text: w.liveText(rec.sealed, rec.answered) }] }] });

  const object = selected.split(':')[0];
  const chain = chains[selected] || active[0].chains[0];
  const graves = active.flatMap((l) => l.chains.flatMap((c) => c.proposals.filter((p) => p.verdict === 'vulcan').map((p) => ({ ...p, object: l.object }))));

  return (
    <div className="book">
      <h1>{w.lanes}</h1>
      <section className="lanes" aria-label={w.lanes}>
        {rows.map((r) => (
          <div key={r.key} className="lane">
            {r.who ? <p className="whose"><span className="mono">{r.who}</span><span>{r.source}</span></p> : <span />}
            <div className="chain">
              {r.nodes.map((n, i) => (
                <div key={i} className="link">
                  {i > 0 && <span aria-hidden="true" />}
                  <Node kind={n.kind} w={w} lines={n.lines} pick={n.pick} pressed={n.pressed} wide={n.wide} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <div className="below">
        <section aria-labelledby="ideas">
          <div className="row"><h2 id="ideas">{w.ideas}</h2><span className="mono">{object}</span></div>
          {chain.proposals.map((p) => {
            const s = spoken(lang, f, p);
            let outcome;
            let tone;
            if (chain.verdict) {
              outcome = p.chosen ? <>{w.chosen}, {E} {f.num(chain.verdict.log10_e, chain.verdict.verdict === 'abstain' ? 2 : 1)}</> : w.notSealed;
              tone = p.chosen ? TONE[chain.verdict.verdict] : 'dim';
            } else {
              outcome = <>{E} {f.num(p.log10_e)}, {w[p.verdict]}, {w.points(p.n)}</>;
              tone = TONE[p.verdict];
            }
            return (
              <article key={`${p.leap}-${p.name}`} className="idea">
                <p className="row"><span className="muted">{w.leaps[p.leap]}</span><span className={`out${tone ? ` ${tone}` : ''}`}>{outcome}</span></p>
                <h3 lang={s.nameLang}>{s.name}</h3>
                <p className="said" lang={s.ideaLang}>{s.idea}</p>
              </article>
            );
          })}
        </section>

        <section aria-labelledby="graves">
          <h2 id="graves">{w.graveyard}</h2>
          {!graves.length && <p className="muted">{w.empty}</p>}
          <ul className="graves">
            {graves.map((g) => {
              const s = spoken(lang, f, g);
              return (
                <li key={`${g.object}-${g.name}`}>
                  <b lang={s.nameLang}>{s.name}</b>
                  <span className="mono">{g.object}</span>
                  <span className="mono">{w.vulcan}, {E} {f.num(g.log10_e)} {w.inN(g.n)}</span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}
