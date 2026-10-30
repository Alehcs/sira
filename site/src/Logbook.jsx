import { useState } from 'react';
import { Tomb } from './pixel.jsx';
import { WORDS, format } from './words.js';

const KIND_COLOR = { surprise: '#FF6AD5', proposals: '#FF6AD5', neptune: '#FF9F43', vulcan: '#8A88B0', adopted: '#FF9F43', abstain: '#5C5A85', quiet: '#3C3A6B' };
const power = (p) => {
  const e = Math.floor(Math.log10(p));
  const m = Math.round(p / 10 ** e);
  const sup = String(e).replace('-', '⁻').replace(/\d/g, (c) => '⁰¹²³⁴⁵⁶⁷⁸⁹'[c]);
  return `p = ${m} × 10${sup}`;
};

function Node({ kind, w, lines, pick, pressed }) {
  const inner = (
    <>
      <span className="kind" style={{ background: KIND_COLOR[kind] }}>{w[kind]}</span>
      <span className="body">{lines.map((l, i) => <span key={i} className={l.mono ? 'mono' : undefined} style={{ color: l.color }}>{l.text}</span>)}</span>
    </>
  );
  if (pick) return <button type="button" className="node" aria-pressed={pressed} onClick={pick}>{inner}</button>;
  return <div className={`node${kind === 'quiet' ? ' wide' : ''}`}>{inner}</div>;
}

function nodesOf(chain, lane, ci, w, f, selected, choose) {
  const muted = '#B8B4E0';
  const out = [
    { kind: 'surprise', lines: [{ text: f.day(chain.at), color: muted }, { text: w.outOf(chain.misses, chain.n) }, { text: power(chain.p), mono: true, color: muted }] },
    {
      kind: 'proposals', key: `${lane.object}:${ci}`,
      lines: chain.proposals.map((p) => ({ text: f.name(p.name), color: p.chosen ? '#FF6AD5' : undefined })).concat([{ text: f.money(chain.cost_usd), mono: true, color: muted }]),
    },
  ];
  if (chain.verdict) {
    const v = chain.verdict;
    out.push({ kind: v.verdict, lines: [{ text: `log10 E ${f.num(v.log10_e, v.verdict === 'abstain' ? 2 : 1)}`, mono: true, color: KIND_COLOR[v.verdict] === '#5C5A85' ? muted : KIND_COLOR[v.verdict] }, { text: w.points(v.n) }] });
    if (lane.adopted && v.verdict === 'neptune') out.push({ kind: 'adopted', lines: [{ text: w.joins }] });
  } else {
    const best = chain.proposals.filter((p) => p.verdict === 'neptune').sort((a, b) => b.log10_e - a.log10_e)[0];
    if (best) out.push({ kind: 'neptune', lines: [{ text: f.name(best.name), color: '#FF9F43' }, { text: `log10 E ${f.num(best.log10_e)}`, mono: true, color: '#FF9F43' }, { text: w.points(best.n) }] });
    chain.proposals.filter((p) => p.verdict === 'vulcan').forEach((p) => out.push({
      kind: 'vulcan', lines: [{ text: f.name(p.name) }, { text: `log10 E ${f.num(p.log10_e)}`, mono: true, color: muted }, { text: w.toGrave, color: muted }],
    }));
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
      nodes: nodesOf(chain, lane, ci, w, f, selected, setSelected),
    });
  }));
  if (quiet.length) rows.push({ key: 'controls', who: quiet.map((l) => l.object).join(' '), source: w.controls, nodes: [{ kind: 'quiet', lines: [{ text: w.quietText }] }] });
  liveChains.forEach((s, i) => {
    const chain = {
      at: s.at, misses: s.misses, n: s.n, p: s.p, cost_usd: s.leap ? s.leap.cost_usd : 0, verdict: s.verdict,
      proposals: s.leap ? s.leap.proposals.map((p) => ({ ...p, chosen: p.name === s.leap.chosen })) : [],
    };
    chains[`${s.object}:live${i}`] = chain;
    rows.push({ key: `live-${i}`, who: s.object, source: w.live, nodes: nodesOf(chain, { object: s.object }, `live${i}`, w, f, selected, setSelected) });
  });
  if (!liveChains.length) rows.push({ key: 'live', who: 'SIRA', source: w.live, nodes: [{ kind: 'quiet', lines: [{ text: w.liveText(rec.sealed, rec.answered) }] }] });

  const object = selected.split(':')[0];
  const chain = chains[selected] || active[0].chains[0];
  const graves = active.flatMap((l) => l.chains.flatMap((c) => c.proposals.filter((p) => p.verdict === 'vulcan').map((p) => ({ ...p, object: l.object }))));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <section className="lanes" aria-label={w.ideas}>
        {rows.map((r) => (
          <div key={r.key} className="lane">
            <div className="who"><span className="mono" style={{ fontSize: 14, wordBreak: 'break-all' }}>{r.who}</span><span className="muted" style={{ fontSize: 14 }}>{r.source}</span></div>
            {r.nodes.map((n, i) => (
              <div key={i} className="link">
                {i > 0 && <span aria-hidden="true" />}
                <Node kind={n.kind} w={w} lines={n.lines} pick={n.pick} pressed={n.pressed} />
              </div>
            ))}
          </div>
        ))}
      </section>

      <div className="cols">
        <section className="panel main" aria-label={w.ideas}>
          <div className="row"><h2 style={{ color: '#FF6AD5' }}>{w.ideas}</h2><span className="mono muted" style={{ fontSize: 14 }}>{object}</span></div>
          {chain.proposals.map((p) => {
            let outcome;
            let color = '#F2F0FF';
            if (chain.verdict) {
              outcome = p.chosen ? `${w.chosen}, log10 E ${f.num(chain.verdict.log10_e, chain.verdict.verdict === 'abstain' ? 2 : 1)}` : w.notSealed;
              color = p.chosen ? KIND_COLOR[chain.verdict.verdict] : '#B8B4E0';
            } else {
              outcome = `log10 E ${f.num(p.log10_e)}, ${w[p.verdict]}, ${w.points(p.n)}`;
              color = KIND_COLOR[p.verdict];
            }
            return (
              <article key={`${p.leap}-${p.name}`} className="idea">
                <div className="row"><span className="muted" style={{ fontSize: 14 }}>{w.leaps[p.leap]}</span><span className="mono" style={{ fontSize: 13, color }}>{outcome}</span></div>
                <span style={{ fontSize: 17, color }}>{f.name(p.name)}</span>
                <q lang="en">{p.idea}</q>
              </article>
            );
          })}
        </section>

        <section className="panel side" aria-label={w.graveyard}>
          <h2 className="muted">{w.graveyard}</h2>
          {graves.map((g) => (
            <div key={`${g.object}-${g.name}`} className="grave">
              <Tomb />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>{f.name(g.name)}</span>
                <span className="mono muted" style={{ fontSize: 13 }}>{g.object}</span>
                <span className="mono muted" style={{ fontSize: 13 }}>{w.vulcan} log10 E {f.num(g.log10_e)}, {w.points(g.n)}</span>
              </div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
