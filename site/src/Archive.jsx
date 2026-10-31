import { useEffect, useMemo, useRef, useState } from 'react';
import { Classes, cost, flux, heard, model, say, who, whole } from './Investigate.jsx';
import Figure from './ui/Figure.jsx';
import Paper from './ui/Paper.jsx';
import Stamps from './ui/Stamps.jsx';
import { Message, Thread } from './ui/Thread.jsx';
import { WORDS, format } from './words.js';
import './archive.css';

const BASE = import.meta.env.BASE_URL;
const mjdOf = (iso) => new Date(iso).getTime() / 86400000 + 40587;
const isoOf = (mjd) => new Date((mjd - 40587) * 86400000).toISOString();
const noon = (night) => `${night}T12:00:00Z`;
const fromHash = () => {
  const [tab, oid] = window.location.hash.slice(1).split('/');
  return tab === 'archive' && oid ? decodeURIComponent(oid) : null;
};
const scoredOf = (o) => o.outcomes.filter((x) => typeof x.log_score === 'number');
const lastOf = (xs) => xs[xs.length - 1];

// what the team last said it is, from the newest bet whose embargo has lifted
function known(o) {
  const b = o.bets.slice().reverse().find((x) => x.open && (x.classes || x.weights));
  if (!b) return null;
  const odds = b.classes || b.weights;
  const [h, p] = Object.entries(odds).filter(([k]) => k !== 'null').sort((x, y) => y[1] - x[1])[0] || [];
  return h ? { bet: b, odds, h, p } : null;
}

function nightsText(nights, lang, f) {
  const months = [];
  nights.forEach((n) => {
    const m = n.slice(0, 7);
    if (!months.length || lastOf(months).m !== m) months.push({ m, days: [] });
    lastOf(months).days.push(Number(n.slice(8)));
  });
  return months.map(({ m, days }) => {
    const name = f.short(noon(`${m}-01`)).replace(/\d+/, '').trim();
    return lang === 'es' ? `${days.join(', ')} ${name}` : `${name} ${days.join(', ')}`;
  }).join('; ');
}

function Row({ o, lang, w, live, hyp, f, onOpen }) {
  const im = o.images || {};
  const read = lastOf(o.reads);
  const look = lastOf(o.lookouts);
  const bet = lastOf(o.bets);
  const what = known(o);
  const shut = o.bets.filter((b) => !b.open);
  const scored = scoredOf(o);
  const call = (r) => w.call(r.label === 'real', f.pct(r.p_real));
  return (
    <li className="arow">
      <div className="thumbs">
        {im.host ? <img src={BASE + im.host} width="64" height="64" alt={live.hostAlt(o.object)} loading="lazy" /> : <span className="gap" />}
        {im.stamps && <Stamps src={BASE + im.stamps} size={[im.panel[0] * 3, im.panel[1]]} tile={im.panel[0]} scale={1} labels={live.panels} alt={live.stampsAlt(o.object)} />}
      </div>
      <div className="aobj">
        <a className="oid" href={`#archive/${o.object}`} onClick={onOpen}>{o.object}</a>
        {o.ra !== null && <span className="coord">{f.ra(o.ra)} {f.dec(o.dec)}</span>}
        <span className="sub">{nightsText(o.nights, lang, f)}</span>
      </div>
      <div className="cells">
        <div><span className="lbl">{w.cols.reader}</span>
          {read ? call(read) : w.noRead}
          {o.reads.slice(0, -1).filter((r) => r.label !== read.label).map((r) => <span key={r.seq} className="sub">{f.short(noon(r.night))}: {call(r)}</span>)}
        </div>
        <div><span className="lbl">{w.cols.lookouts}</span>
          {look ? (look.picked ? w.yes : w.no) : w.noLooks}
          {look && <span className="sub">{w.priority(f.num(look.priority, 2))}</span>}
        </div>
        <div><span className="lbl">{w.cols.what}</span>
          {what ? hyp[what.h] || what.h : shut.length ? <span className="muted">{w.opens(f.short(shut[0].open_at))}</span> : '—'}
          {what && <span className="sub">{f.pct(what.p)}, {f.short(noon(what.bet.night))}</span>}
        </div>
        <div><span className="lbl">{w.cols.bets}</span>
          {bet ? w.bets(o.bets.length) : w.none}
          {bet && <span className="sub">{f.short(noon(bet.night))}: {f.pct(bet.question.p)}{bet.term ? ` ${f.term(bet.term)}` : ''}{bet.model === 'v0' ? ', v0' : ''}</span>}
        </div>
        <div><span className="lbl">{w.cols.sky}</span>
          {o.outcomes.length ? w.measurements(o.outcomes.length) : <span className="muted">{bet ? w.waiting : '—'}</span>}
          {scored.length > 0 && <span className="sub">{w.score} {scored.map((x) => f.num(x.log_score, 2)).join(' ')}</span>}
          {!scored.length && o.outcomes.length > 0 && <span className="sub">{w.unscored(f.short(shut.length ? shut[0].open_at : o.outcomes[0].at))}</span>}
        </div>
      </div>
    </li>
  );
}

function List({ book, lang, w, live, hyp, f, keep }) {
  const [q, setQ] = useState('');
  const [night, setNight] = useState('all');
  const [reader, setReader] = useState('all');
  const [looks, setLooks] = useState('all');
  const [withBet, setWithBet] = useState(false);
  const [withScored, setWithScored] = useState(false);
  const [sort, setSort] = useState('night');
  const objs = book.objects;
  const nights = book.nights.slice().reverse();
  const since = book.nights.length ? f.day(noon(book.nights[0].night)) : '';
  const scoredAll = objs.reduce((n, o) => n + scoredOf(o).length, 0);
  const betsAll = objs.reduce((n, o) => n + o.bets.length, 0);
  const prio = (o) => (o.lookouts.length ? lastOf(o.lookouts).priority : -1);

  const rows = objs.filter((o) => {
    const read = lastOf(o.reads);
    const look = lastOf(o.lookouts);
    if (q && !o.object.toLowerCase().includes(q.trim().toLowerCase())) return false;
    if (night !== 'all' && !o.nights.includes(night)) return false;
    if (reader !== 'all' && (!read || read.label !== reader)) return false;
    if (looks !== 'all' && (!look || look.picked !== (looks === 'yes'))) return false;
    if (withBet && !o.bets.length) return false;
    return !withScored || scoredOf(o).length > 0;
  });
  const order = {
    night: (a, b) => b.last.localeCompare(a.last) || prio(b) - prio(a) || a.object.localeCompare(b.object),
    priority: (a, b) => prio(b) - prio(a),
    reader: (a, b) => ((lastOf(b.reads) || {}).p_real ?? -1) - ((lastOf(a.reads) || {}).p_real ?? -1),
    bets: (a, b) => b.bets.length - a.bets.length || prio(b) - prio(a),
    name: (a, b) => a.object.localeCompare(b.object),
  }[sort];
  rows.sort(order);
  // grouped by night only when sorted by it
  const groups = [];
  rows.forEach((o) => {
    const key = sort === 'night' ? (night === 'all' ? o.last : night) : '';
    if (!groups.length || lastOf(groups).key !== key) groups.push({ key, rows: [] });
    lastOf(groups).rows.push(o);
  });
  const open = () => { keep.current = window.scrollY; };
  const seg = (value, set, options) => (
    <div className="seg">
      {Object.entries(options).map(([k, name]) => <button key={k} type="button" aria-pressed={value === k} onClick={() => set(k)}>{name}</button>)}
    </div>
  );

  return (
    <>
      <div className="archead">
        <div>
          <h1>{w.title}</h1>
          <p>{w.counts(objs.length, since, betsAll, scoredAll)}</p>
        </div>
        {book.head && book.head.tsa_time && <p className="prov">{live.sealed(f.stamp(book.head.tsa_time), book.head.hash.slice(0, 8))}</p>}
      </div>
      <div className="filters">
        <div className="frow">
          <input type="search" className="find" value={q} placeholder={w.search} aria-label={w.searchLabel} onChange={(e) => setQ(e.target.value)} />
          <div className="fgroup" role="group" aria-label={w.night}>
            <span className="flabel">{w.night}</span>
            <div className="nchips">
              <button type="button" aria-pressed={night === 'all'} onClick={() => setNight('all')}><b>{w.all}</b><span>{w.objects(objs.length)}</span></button>
              {nights.map((n) => (
                <button key={n.night} type="button" aria-pressed={night === n.night} onClick={() => setNight(n.night)}>
                  <b>{f.short(noon(n.night))}</b><span>{w.objects(objs.filter((o) => o.nights.includes(n.night)).length)}</span>
                </button>
              ))}
            </div>
          </div>
          <label className="fgroup">
            <span className="flabel">{w.sort}</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {Object.entries(w.sorts).map(([k, name]) => <option key={k} value={k}>{name}</option>)}
            </select>
          </label>
        </div>
        <div className="frow">
          <div className="fgroup" role="group" aria-label={w.reader}><span className="flabel">{w.reader}</span>{seg(reader, setReader, w.readers)}</div>
          <div className="fgroup" role="group" aria-label={w.lookouts}><span className="flabel">{w.lookouts}</span>{seg(looks, setLooks, w.looks)}</div>
          <label className="check"><input type="checkbox" checked={withBet} onChange={(e) => setWithBet(e.target.checked)} />{w.withBet}</label>
          <label className="check"><input type="checkbox" checked={withScored} onChange={(e) => setWithScored(e.target.checked)} />{w.withScored}</label>
          <div className="downloads">
            <span className="n">{w.objects(rows.length)}</span>
            <a href={`${BASE}data/archive.csv`} download>{w.csv}</a>
            <a href={`${BASE}data/archive.json`} download>{w.json}</a>
          </div>
        </div>
      </div>
      <div className="ahead" aria-hidden="true">
        <div className="thumbs">{[w.cols.host, ...live.panels].map((c) => <span key={c}>{c}</span>)}</div>
        <span>{w.cols.object}</span>
        <div className="cells">{['reader', 'lookouts', 'what', 'bets', 'sky'].map((c) => <span key={c}>{w.cols[c]}</span>)}</div>
      </div>
      {!rows.length && <p className="muted">{w.empty}</p>}
      {groups.map((g, i) => {
        const n = book.nights.find((x) => x.night === g.key);
        return (
          <section key={g.key || 'all'} className="agroup" aria-label={g.key ? f.day(noon(g.key)) : w.title}>
            {g.key && (
              <h2 className="nighthead">
                <span className="date">{f.day(noon(g.key))}</span>
                {n && <span className="hm">{w.chile(f.chile(n.start))}</span>}
                {i === 0 && g.key === lastOf(book.nights).night && <a href="#live">{w.investigate}</a>}
              </h2>
            )}
            <ol className="arows">
              {g.rows.map((o) => <Row key={o.object} o={o} lang={lang} w={w} live={live} hyp={hyp} f={f} onOpen={open} />)}
            </ol>
          </section>
        );
      })}
    </>
  );
}

// the curve SIRA saw when it last bet, the measurements since and every sealed forecast it may show
function curves(o, cand, now) {
  const t0 = mjdOf(now);
  const open = o.bets.filter((b) => b.open);
  const base = open.slice().reverse().find((b) => b.seen) ? open.slice().reverse().find((b) => b.seen).seen : (cand && cand.curve) || [];
  const points = base.map(([mjd, band, kind, v, err]) => ({ mjd, day: mjd - t0, band: band.slice(-1), flux: v, err, limit: kind !== 'det' }));
  const known = new Set(points.map((p) => p.mjd.toFixed(4)));
  o.outcomes.forEach((x) => {
    if (x.flux === null || known.has(x.mjd.toFixed(4))) return;
    points.push({ mjd: x.mjd, day: x.mjd - t0, band: x.band.slice(-1), flux: x.kind === 'det' ? x.flux : x.limit || x.flux, err: x.flux_err, limit: x.kind !== 'det' });
  });
  const fanned = open.filter((b) => b.fan);
  const last = lastOf(fanned);
  const forecasts = fanned.flatMap((b) => ['ztfg', 'ztfr'].filter((band) => b.fan[band] && b.fan[band].length).map((band) => ({
    band: band.slice(-1), rows: b.fan[band].map(([mjd, mu, sd]) => [mjd - t0, mu, sd]), style: b === last ? 'sealed' : 'old',
    label: b === last && band === 'ztfr' ? `${b.hash.slice(0, 8)} ${b.model}` : null,
  })));
  return { points: points.filter((p) => p.flux > 0), forecasts, last, t0 };
}

function Scores({ o, w, f }) {
  if (!o.outcomes.length) return null;
  const night = Object.fromEntries(o.bets.map((b) => [b.bet, b.night]));
  const t = w.table;
  return (
    <section>
      <h2 className="oh2">{w.scored}</h2>
      <table className="scores">
        <thead><tr><th>{t.band}</th><th>{t.at}</th><th className="n">{t.flux}</th><th className="n">{t.log}</th><th className="n">{t.pit}</th><th>{t.bet}</th></tr></thead>
        <tbody>
          {o.outcomes.map((x) => (
            <tr key={`${x.bet}${x.mjd}`}>
              <td>{x.band.slice(-1)}</td>
              <td>{f.stamp(isoOf(x.mjd)).replace(/ \d{4} /, ' ').replace(' UTC', '')}</td>
              <td className="n">{x.flux === null ? '—' : `${f.num(x.flux, 1)} ± ${f.num(x.flux_err || 0, 1)}`}</td>
              <td className="n">{typeof x.log_score === 'number' ? f.num(x.log_score, 2) : '—'}</td>
              <td className="n">{typeof x.pit === 'number' ? f.num(x.pit, 2) : '—'}</td>
              <td>{night[x.bet] ? f.short(noon(night[x.bet])) : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Record({ b, o, due, w, f }) {
  const a = o.answers.find((x) => x.bet === b.bet && x.which === b.staked);
  let answer = { text: w.waitingAnswer(f.day(due || b.question.due)) };
  if (a && a.void) answer = { text: w.void };
  else if (a) answer = { text: w.answer(a.yes), detail: `${w.score} ${f.num(a.log_score, 2)}`, tone: (b.question.p >= 0.5) === a.yes ? 'ok' : 'warn' };
  return (
    <Paper question={f.question(b.question)} p={f.pct(b.question.p)} term={f.term(b.term)} hash={b.hash.slice(0, 12)} time={f.stamp(b.sealed_at || b.at)} answer={answer}>
      <p className="line">{w.models[b.model] || b.model}</p>
    </Paper>
  );
}

// the night's voices in the order the ledger sealed them, with the sky's measurements among them
function notes(o) {
  const items = [
    ...o.looks.map((x) => ({ ...x, role: 'lookout' })),
    ...o.reads.map((x) => ({ ...x, role: 'reader', decision: x.label ? `${x.label} (${x.p_real})` : '' })),
    ...o.team,
    ...o.bets.filter((b) => b.model === 'v0').map((b) => ({ role: 'v0', night: b.night, at: b.at, seq: b.seq, bet: b })),
    ...o.outcomes.map((x) => ({ ...x, role: 'sky' })),
    ...o.answers.map((x) => ({ ...x, role: 'sky', answer: true })),
  ];
  return items.sort((a, b) => a.night.localeCompare(b.night) || a.at.localeCompare(b.at) || (a.seq || 0) - (b.seq || 0));
}

function Notes({ o, book, lang, w, live, hyp, f }) {
  const items = notes(o);
  const bets = Object.fromEntries(o.bets.map((b) => [b.bet, b]));
  const teamBet = (night) => o.bets.find((b) => b.night === night && b.model === 'v1' && b.open);
  const out = [];
  o.nights.forEach((night) => {
    const n = book.nights.find((x) => x.night === night);
    out.push(
      <li key={`n${night}`} className="nightsep">
        <h3>{f.day(noon(night))}</h3>
        {n && <span>{w.chile(f.chile(n.start))}</span>}
      </li>,
    );
    items.filter((s) => s.night === night).forEach((s, i) => {
      const key = `${night}${i}`;
      const bet = teamBet(night);
      if (s.role === 'sky') {
        const of = bets[s.bet];
        const day = of ? f.short(noon(of.night)) : '';
        const text = s.answer
          ? (s.void ? w.voided(day) : w.answered(s.yes, day))
          : `${w.measured(s.band.slice(-1), f.num(s.flux || s.limit || 0, 1), f.num(s.flux_err || 0, 1))}${typeof s.log_score === 'number' ? w.forBet(f.num(s.log_score, 2), day) : ''}.`;
        out.push(<Message key={key} mark={live.marks.sky} name={live.roles.sky} model="ZTF" when={f.stamp(s.answer ? s.at : isoOf(s.mjd))} at={s.at} text={text} />);
        return;
      }
      if (s.role === 'v0') {
        const b = s.bet;
        const weights = b.weights ? Object.entries(b.weights).sort((x, y) => y[1] - x[1]).map(([h, v]) => `${hyp[h] || h} ${f.pct(v)}`).join(', ') : null;
        out.push(
          <Message key={key} mark={live.marks.v0} name={live.roles.v0} model="v0" when={f.stamp(b.at)} at={b.at} text={w.seals}>
            {(weights || (b.killed && Object.keys(b.killed).length > 0)) && (
              <dl className="lines">
                {weights && <><dt>{w.weights}</dt><dd>{weights}</dd></>}
                {b.killed && Object.entries(b.killed).flatMap(([h, why]) => [<dt key={`k${h}`}>{w.killed}</dt>, <dd key={`d${h}`}>{hyp[h] || h}: <span lang="en">{why}</span></dd>])}
              </dl>
            )}
          </Message>,
        );
        return;
      }
      const words = s.why || heard(s, bet && bet.skeptics, hyp);
      const theory = s.role === 'theorist' && bet && (bet.theories || []).find((t) => `defends ${t.hypothesis}` === s.decision);
      out.push(
        <Message key={key} mark={live.marks[s.role] || '?'} name={who(s, live)} model={model(s)}
          when={typeof s.seconds === 'number' ? `${f.num(s.seconds, 0)} s` : null} at={`PT${Math.round(s.seconds || 0)}S`}
          cost={s.cost_usd ? cost(lang, f, s.cost_usd) : null} text={say(s, live, f, hyp)} quote={words ? { text: words, lang: 'en' } : null}>
          {theory && theory.weakest_point && <dl className="lines"><dt>{w.weak}</dt><dd lang="en">{whole(theory.weakest_point)}</dd></dl>}
          {s.role === 'forecaster' && bet && (bet.classes || bet.weights) && <Classes odds={bet.classes || bet.weights} hyp={hyp} f={f} />}
        </Message>,
      );
    });
    if (o.shut[night]) out.push(<li key={`s${night}`} className="shutnote">{w.shut(f.stamp(o.shut[night]))}</li>);
  });
  return <Thread lang={lang} label={w.nights} current={o.object}>{out}</Thread>;
}

function Downloads({ o, w }) {
  const [csv, setCsv] = useState(null);
  const json = useMemo(() => URL.createObjectURL(new Blob([JSON.stringify(o, null, 1)], { type: 'application/json' })), [o]);
  useEffect(() => {
    let url = null;
    fetch(`${BASE}data/archive.csv`).then((r) => (r.ok ? r.text() : null)).then((text) => {
      if (!text) return;
      const lines = text.split('\n');
      url = URL.createObjectURL(new Blob([[lines[0], ...lines.filter((l) => l.startsWith(`${o.object},`))].join('\n')], { type: 'text/csv' }));
      setCsv(url);
    }).catch(() => setCsv(null));
    return () => { URL.revokeObjectURL(json); if (url) URL.revokeObjectURL(url); };
  }, [o]);
  return (
    <>
      <a href={json} download={`${o.object}.json`}>{w.json}</a>
      {csv && <a href={csv} download={`${o.object}.csv`}>{w.csv}</a>}
    </>
  );
}

function Obj({ o, book, lang, w, live, hyp, f, liveData }) {
  const im = o.images || {};
  const read = lastOf(o.reads);
  const look = lastOf(o.lookouts);
  const what = known(o);
  const shut = o.bets.filter((b) => !b.open);
  const cand = liveData && liveData.candidates.find((c) => c.object === o.object);
  const dues = Object.fromEntries(((liveData && liveData.telegrams) || []).map((t) => [t.bet, t.answer_due]));
  const { points, forecasts, last, t0 } = curves(o, cand, book.built_at);
  const models = {};
  o.bets.forEach((b) => { models[b.model] = (models[b.model] || 0) + 1; });
  const answered = o.answers.filter((a) => !a.void).length;
  const lv = `https://www.legacysurvey.org/viewer?ra=${o.ra}&dec=${o.dec}&layer=ls-dr10&zoom=16&mark=${o.ra},${o.dec}`;
  const mjd = o.first_detection ? mjdOf(o.first_detection) : null;

  // the forecast window: a week before the last open bet to the end of its fan
  let zoom = null;
  if (last) {
    const made = mjdOf(last.made_at) - t0;
    const end = Math.max(0, ...forecasts.filter((fc) => fc.style === 'sealed').flatMap((fc) => fc.rows.map((r) => r[0]))) + 1;
    const x = [Math.floor(made - 5), Math.ceil(end)];
    const inside = points.filter((p) => p.day >= x[0] && p.day <= x[1] && !p.limit).map((p) => p.flux)
      .concat(forecasts.filter((fc) => fc.style === 'sealed').flatMap((fc) => fc.rows.flatMap((r) => [r[1] + r[2], Math.max(r[1] - r[2], r[1] / 2)])), last.question.reference);
    const q = last.question;
    zoom = {
      x, y: [Math.min(...inside) / 1.25, Math.max(...inside) * 1.25],
      reference: { flux: q.reference, label: live.at(flux(f, q.reference), q.band) },
      target: { day: mjdOf(q.due) - t0, label: f.short(q.due) },
    };
  }

  return (
    <>
      <a className="back" href="#archive">{w.back}</a>
      <div className="ohead">
        <div>
          <h1>{o.object}</h1>
          <div className="coords">
            {o.ra !== null && <span><b>{f.ra(o.ra)} {f.dec(o.dec)}</b></span>}
            {o.l !== null && <span>l {f.num(o.l, 2)}° b {o.b >= 0 ? '+' : ''}{f.num(o.b, 2)}°</span>}
            {o.first_detection && <span>{w.first} {f.stamp(o.first_detection)}</span>}
            {mjd && <span>MJD {f.num(mjd, 2)}</span>}
          </div>
          <div className="olinks">
            <a href={`https://alerce.online/object/${o.object}`} target="_blank" rel="noreferrer">ALeRCE</a>
            {o.ra !== null && <a href={lv} target="_blank" rel="noreferrer">{w.legacy}</a>}
            {o.tns && <a href={`https://www.wis-tns.org/object/${o.tns}`} target="_blank" rel="noreferrer">TNS</a>}
            {o.bets.length > 0 && <a href="#telegrams">{w.forecasts(o.bets.length)}</a>}
            <Downloads o={o} w={w} />
          </div>
        </div>
        <dl className="ostate">
          <dt>{w.cols.reader}</dt>
          <dd>{read ? w.call(read.label === 'real', f.pct(read.p_real)) : w.noRead}{read && <span className="when">{f.short(noon(read.night))}</span>}</dd>
          <dt>{w.cols.lookouts}</dt>
          <dd>{look ? `${look.picked ? w.yes : w.no}, ${w.priority(f.num(look.priority, 2))}` : w.noLooks}{look && <span className="when">{f.short(noon(look.night))}</span>}</dd>
          <dt>{w.cols.bets}</dt>
          <dd>{o.bets.length ? w.sealedBets(o.bets.length, Object.entries(models).map(([m, n]) => w.byModel(n, w.models[m] || m))) : w.none}</dd>
          <dt>{w.cols.sky}</dt>
          <dd>{w.skyState(scoredOf(o).length, answered)}</dd>
        </dl>
      </div>

      <div className="oband">
        <div className="oleft">
          {im.stamps && <Stamps src={BASE + im.stamps} size={[im.panel[0] * 3, im.panel[1]]} tile={im.panel[0]} scale={2} labels={live.panels} alt={live.stampsAlt(o.object)} arcsec={10} />}
          <div className="hostrow">
            {im.host && <img className="ohost" src={BASE + im.host} width="256" height="256" alt={live.hostAlt(o.object)} />}
            <section>
              {what && <h2 className="oh2">{w.what(f.short(noon(what.bet.night)))}</h2>}
              {what && <Classes odds={what.odds} hyp={hyp} f={f} />}
              {!what && shut.length > 0 && <p className="muted">{w.opens(f.short(shut[0].open_at))}</p>}
            </section>
          </div>
          <Scores o={o} w={w} f={f} />
        </div>
        <div className="oright">
          {points.length > 0 && <Figure lang={lang} start={book.built_at} points={points} forecasts={forecasts} now={0} label={w.chart(o.object)} />}
          {zoom && <Figure lang={lang} start={book.built_at} points={points} forecasts={forecasts} now={0} x={zoom.x} y={zoom.y}
            reference={zoom.reference} target={zoom.target} label={w.zoom(o.object)} />}
        </div>
      </div>

      <h2 className="osect">{w.nights}</h2>
      <div className="onights">
        <Notes o={o} book={book} lang={lang} w={w} live={live} hyp={hyp} f={f} />
        {o.bets.length > 0 && (
          <section className="papers" aria-label={w.sealedRecords}>
            {o.bets.slice().reverse().map((b) => <Record key={b.bet} b={b} o={o} due={dues[b.bet]} w={w} f={f} />)}
          </section>
        )}
      </div>
    </>
  );
}

export default function Archive({ lang, live }) {
  const [book, setBook] = useState(null);
  const [oid, setOid] = useState(fromHash);
  const keep = useRef(0);
  const w = WORDS[lang].archive;
  const lw = WORDS[lang].live;
  const hyp = { ...WORDS[lang].lab.hyp, other: lw.other };
  const f = format(lang);

  useEffect(() => {
    fetch(`${BASE}data/archive.json`).then((r) => (r.ok ? r.json() : null)).then(setBook).catch(() => setBook(null));
    const follow = () => setOid(fromHash());
    window.addEventListener('hashchange', follow);
    return () => window.removeEventListener('hashchange', follow);
  }, []);
  useEffect(() => { window.scrollTo(0, oid ? 0 : keep.current); }, [oid]);

  if (!book) return <p className="muted">{WORDS[lang].loading}</p>;
  if (oid) {
    const o = book.objects.find((x) => x.object === oid);
    if (!o) return <><a className="back" href="#archive">{w.back}</a><p className="muted">{w.missing}</p></>;
    return <Obj o={o} book={book} lang={lang} w={w} live={lw} hyp={hyp} f={f} liveData={live} />;
  }
  return <List book={book} lang={lang} w={w} live={lw} hyp={hyp} f={f} keep={keep} />;
}
