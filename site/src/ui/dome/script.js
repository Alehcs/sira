// each beat as the observatory plays it: who thinks for how long, then who says what to whom
const LEAD = 0.4;
const THINK = 2.4; // the longest call of a beat takes this long on screen, its real seconds counted on its bubble
const TALK = 2.2;
const SEATS = ['tia', 'tibc', 'tii'];
const WHO = { reader: 'lec', llm_only: 'muse', director: 'dir', senior: 'sen', forecaster: 'pro', leverrier: 'lv', sky: 'ztf', lookouts: 'vig' };
const LENSES = { instrument: 'ein', physics: 'efi', memory: 'eme' };

const hyp = (c) => (c.decision || '').replace('defends ', '');

// each hypothesis keeps its board; a new one takes a board nobody in this beat defends
function seat(calls, seats) {
  const hyps = calls.filter((c) => c.role === 'theorist').map(hyp);
  const next = { ...seats };
  const free = SEATS.filter((s) => !hyps.includes(next[s]));
  for (const h of hyps) if (!SEATS.some((s) => next[s] === h) && free.length) next[free.shift()] = h;
  return next;
}

const agent = (c, seats) => (c.role === 'theorist' ? SEATS.find((s) => seats[s] === hyp(c)) : c.role === 'skeptic' ? LENSES[c.lens] : WHO[c.role]);

// who a line is for: the reader tells the theorists, a skeptic answers whoever it doubts, the rest report to the director
function audience(c, seats) {
  if (c.to) return c.to.flatMap((r) => (r === 'theorist' ? SEATS : [WHO[r]])).filter(Boolean);
  if (c.role === 'reader') return SEATS;
  if (c.role === 'skeptic' && c.lens === 'instrument') return ['lec'];
  if (c.role === 'skeptic' && c.lens === 'physics') {
    const doubted = (c.decision || '').replace('doubts ', '').split(', ');
    const at = SEATS.filter((s) => doubted.includes(seats[s]));
    return at.length ? at : ['dir'];
  }
  if (c.role === 'director') return ['pro'];
  if (c.role === 'forecaster') return ['printer'];
  return ['dir'];
}

// the whole story at once, so a beat knows what earlier beats left behind: the boards, Le Verrier awake, the last slip
export function plan(beats, line) {
  let seats = { tia: 'ia', tibc: 'ibc', tii: 'ii' };
  let woke = null;
  let chalked = null;
  let slip = null;
  return beats.map((b, i) => {
    seats = seat(b.calls, seats);
    const by = new Map();
    for (const c of b.calls) {
      const who = agent(c, seats);
      if (!who) continue;
      const was = by.get(who);
      const own = c.pending ? Infinity : c.seconds;
      if (!was) by.set(who, { who, call: c, seconds: own });
      else {
        was.seconds = Math.max(was.seconds ?? 0, own ?? 0);
        if (c.says || !was.call.says) was.call = c;
      }
    }
    const agents = [...by.values()];
    const wakes = woke === null && by.has('lv');
    if (wakes) woke = i;
    const longest = Math.max(0, ...agents.map((a) => a.seconds).filter((s) => s > 0 && s < Infinity));
    // a live beat runs in real time
    const k = b.live ? 1 : Math.max(1, longest / THINK);
    const events = agents.map(({ who, call, seconds }) => {
      const from = LEAD + (who === 'ztf' ? 1.2 : who === 'lv' && wakes ? 0.6 : 0);
      const end = seconds > 0 ? from + seconds / k : from + 0.3;
      return { who, from, end, real: seconds, k, text: call.says || line(call), to: audience(call, seats), says: !!call.says };
    });
    const ends = events.map((e) => e.end).filter((e) => e < Infinity);
    const last = Math.max(LEAD, ...ends);
    const holder = events.find((e) => e.says) || events.find((e) => e.end === last);
    for (const e of events) e.until = e === holder ? Infinity : e.end + TALK;
    const pro = events.find((e) => e.who === 'pro');
    const seal = b.seal == null ? null : { at: pro ? pro.end : LEAD + 0.6, p: b.seal };
    const chalk = chalked === null && b.scene && b.scene.lens && events.find((e) => e.who === 'lv' && e.real > 0);
    if (chalk) chalked = i;
    const out = {
      events, seats, seal, before: slip, length: events.some((e) => e.end === Infinity) ? Infinity : last + TALK + 0.4,
      asleep: woke === null || i < woke, wake: wakes ? LEAD : null, chalk: chalk ? [chalk.from, chalk.end] : chalked !== null && chalked < i,
      pulse: events.some((e) => e.who === 'lec' && e.real > 0) ? LEAD : events.some((e) => e.who === 'ztf') ? LEAD : null,
      sky: events.some((e) => e.who === 'ztf'),
    };
    if (seal) slip = seal.p;
    return out;
  });
}

// what everyone is doing at time t into a beat
export function moment(p, t) {
  const st = { agents: {}, talks: [], seats: p.seats };
  for (const e of p.events) {
    if (t >= e.from && t < e.end && e.real > 0) st.agents[e.who] = { think: true, real: e.real === Infinity ? t - e.from : Math.min(e.real, (t - e.from) * e.k) };
    else if (t >= e.end && t < e.until) {
      st.agents[e.who] = { talk: true, text: e.text, to: e.to };
      st.talks.push(e);
    }
  }
  st.pulse = p.pulse !== null && t >= p.pulse && t < p.pulse + 1.2 ? (t - p.pulse) / 1.2 : null;
  st.exposing = p.sky && t >= LEAD - 0.2 && t < LEAD + 1.2;
  const printed = p.seal && t >= p.seal.at;
  st.sealed = printed ? p.seal.p : p.before;
  st.slip = printed ? Math.min(1, (t - p.seal.at) / 0.8) : p.before !== null ? 1 : 0;
  st.keying = !!printed && t < p.seal.at + 1.4;
  st.asleep = p.asleep || (p.wake !== null && t < p.wake + 0.4);
  st.alarm = p.wake !== null && t >= p.wake - 0.4 && t < p.wake + 2.4 && Math.floor(t * 4) % 2 === 0;
  st.chalk = Array.isArray(p.chalk) ? Math.max(0, Math.min(1, (t - p.chalk[0]) / (p.chalk[1] - p.chalk[0]))) : p.chalk ? 1 : 0;
  const busy = (id) => !!(st.agents[id] && st.agents[id].think);
  st.blinking = busy('lec');
  st.instrument = busy('ein');
  st.drawer = busy('eme');
  return st;
}

// how long each beat lasts, for whoever plays the beats one after another
export const lengths = (beats) => plan(beats, () => '').map((p) => p.length);
