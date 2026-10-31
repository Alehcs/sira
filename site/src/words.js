// every visible word in both languages, plus the number and date formats each one uses

const MONTHS = {
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
  es: ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
};

const IPCC_ES = {
  'virtually certain': 'virtualmente cierto', 'very likely': 'muy probable', likely: 'probable',
  'about as likely as not': 'tan probable como improbable', unlikely: 'improbable', 'very unlikely': 'muy improbable',
  'exceptionally unlikely': 'excepcionalmente improbable',
};

const NAMES_ES = {
  'Unseen foreground microlens': 'Microlente invisible en primer plano',
  'Galactic microlensing event': 'Evento de microlente galáctica',
  'Drifting zeropoint subtraction bias': 'Sesgo por deriva del punto cero',
  'Microlensed underlying supernova': 'Supernova de fondo con microlente',
  'Galactic point-lens microlensing': 'Microlente puntual galáctica',
  'Drifting template subtraction leakage': 'Fuga por deriva de la plantilla',
  'Lens on red background giant': 'Lente sobre una gigante roja de fondo',
  'Microlensed red giant': 'Gigante roja con microlente',
  'Red template subtraction drift': 'Deriva de la resta con plantilla roja',
  'Foreground microlens magnification': 'Magnificación por microlente en primer plano',
  'Drifting calibration subtraction residual': 'Residuo de calibración a la deriva',
};

export function format(lang) {
  const es = lang === 'es';
  const decimal = (s) => (es ? s.replace('.', ',') : s);
  const num = (v, digits = 1) => decimal(Number(v).toFixed(digits)).replace('-', '−');
  // a no-break space keeps 46,7 % and US$ 0,01 on one line
  const pct = (p) => {
    const n = Math.round(p * 1000) / 10;
    const s = decimal(Number.isInteger(n) ? String(n) : n.toFixed(1));
    return es ? `${s} %` : `${s}%`;
  };
  const money = (v) => (es ? `US$ ${decimal(v.toFixed(2))}` : `US$${v.toFixed(2)}`);
  const sexagesimal = (v, digits) => {
    const total = Number((Math.abs(v) * 3600).toFixed(digits));
    const s = (total % 60).toFixed(digits);
    return [Math.floor(total / 3600), String(Math.floor(total / 60) % 60).padStart(2, '0'), decimal(s.padStart(digits + 3, '0'))];
  };
  const ra = (deg) => { const [h, m, s] = sexagesimal(deg / 15, 2); return `${h}h${m}m${s}s`; };
  const dec = (deg) => { const [d, m, s] = sexagesimal(deg, 1); return `${deg < 0 ? '−' : '+'}${d}°${m}′${s}″`; };
  const day = (iso) => {
    const d = new Date(iso);
    const m = MONTHS[lang][d.getUTCMonth()];
    return es ? `${d.getUTCDate()} ${m} ${d.getUTCFullYear()}` : `${m} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
  };
  const short = (iso) => {
    const d = new Date(iso);
    const m = MONTHS[lang][d.getUTCMonth()];
    return es ? `${d.getUTCDate()} ${m}` : `${m} ${d.getUTCDate()}`;
  };
  const stamp = (iso) => {
    const d = new Date(iso);
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    return `${d.getUTCDate()} ${MONTHS[lang][d.getUTCMonth()]} ${d.getUTCFullYear()} ${hh}:${mm} UTC`;
  };
  const chile = (iso) => new Intl.DateTimeFormat(es ? 'es-CL' : 'en-US', {
    timeZone: 'America/Santiago', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(iso));
  const term = (t) => (t ? (es ? IPCC_ES[t] || t : t) : '');
  const name = (n) => (es ? NAMES_ES[n] || n : n);
  const question = (q) => {
    const ref = decimal(String(q.reference));
    if (q.kind === 'level') {
      const more = q.direction === 'above';
      return es
        ? `¿Más ${more ? 'brillante' : 'débil'} que ${ref} μJy en ${q.band} en ${q.days} días?`
        : `${more ? 'Brighter' : 'Fainter'} than ${ref} μJy in ${q.band} in ${q.days} days?`;
    }
    return es
      ? `¿Más brillante en ${q.band} en ${q.days} días que en su última detección en ${q.band} (${ref} μJy)?`
      : `Brighter in ${q.band} in ${q.days} days than at its last ${q.band} detection (${ref} μJy)?`;
  };
  return { num, pct, money, ra, dec, day, short, stamp, chile, term, name, question };
}

export const WORDS = {
  en: {
    tagline: 'An AI astronomer built to be proven wrong in public',
    tabs: { lab: 'Lab', live: 'Investigate', beat: 'Beat SIRA', telegrams: 'Forecasts', logbook: 'Logbook' },
    sections: 'Sections', language: 'Language', theme: 'Theme', themes: { dark: 'Dark', light: 'Light' },
    repo: 'Code', ledger: 'Public ledger', protocol: 'Protocol', loading: 'Loading…',
    credits: 'Images: Pan-STARRS1 via the Legacy Surveys viewer; Legacy Surveys / D. Lang (Perimeter Institute), CC BY 4.0; ZTF via ALeRCE.',
    fig: { days: 'days', now: 'now' },
    thread: { more: 'More below' },
    dome: {
      label: 'Cutaway of SIRA’s observatory: the telescope under the dome, the lab and the control room, with the team at work',
      names: {
        vig: 'Lookouts', lec: 'Reader', ein: 'Instrument skeptic', efi: 'Physics skeptic', eme: 'Memory skeptic', muse: 'Muse alone',
        dir: 'Director', sen: 'Senior', pro: 'Forecaster', lv: 'Le Verrier', ztf: 'ZTF',
      },
      hyp: { ia: 'Ia', ibc: 'Ibc', ii: 'II', tde: 'TDE', adopted: 'the lens' },
      theorist: (h) => (h === 'adopted' ? 'Lens theorist' : `Theorist ${h}`),
      seconds: (n) => `${n}\u00a0s`,
      reads: (real, p) => (real ? `Sees a real source (${p}).` : `A bad subtraction? ${p} real.`),
      defends: (h) => `Defends ${h}.`, realSource: 'Sees a real source.', artifact: 'It is an artifact.',
      doubts: (hs) => `Doubts ${hs.length > 1 ? `${hs.slice(0, -1).join(', ')} and ${hs[hs.length - 1]}` : hs[0]}.`,
      noObjection: 'No objection.', recognises: 'Recognizes it.', forgets: 'Does not recognize it.',
      alone: (n) => `Forecasts ${n} points on its own.`,
      directs: (action) => (action === 'escalate' ? 'Asks the senior.' : action === 'bet' ? 'Picks the question to stake.' : 'Reviews the bet.'),
      words: 'Words the bet.', proposes: (name) => `Proposes “${name}”.`,
    },
    lab: {
      names: { dome: 'Reader', theory: 'Theorists', skeptics: 'Skeptics', forecaster: 'Forecaster', director: 'Director', leverrier: 'Le Verrier', sky: 'The sky' },
      marks: { dome: 'R', theory: 'T', skeptics: 'S', forecaster: 'F', director: 'D', leverrier: 'LV', sky: 'ZTF' },
      panels: ['science', 'reference', 'difference', 'zoom ×3'],
      stampsAlt: (oid) => `First ZTF images of ${oid}: science, reference, difference and zoom`,
      skyAlt: (oid) => `Pan-STARRS1 field around ${oid}`, first: 'first detection',
      hyp: { ia: 'Type Ia supernova', ibc: 'Type Ibc supernova', ii: 'Type II supernova', tde: 'Tidal disruption', null: 'None of the above', adopted: 'Invisible lens' },
      lenses: { instrument: 'Instrument skeptic', physics: 'Physics skeptic', memory: 'Memory skeptic' },
      realSource: 'sees a real source', artifact: 'calls it an artifact', doubts: (hs) => `doubts ${hs.join(', ')}`,
      recognises: 'recognizes it', forgets: 'does not recognize it',
      choices: { wait: 'Wait', think: 'Think', escalate: 'Escalate', ask: 'Ask' },
      measurements: (n) => `${n} measurements`, outside: (a, b) => `${a} of ${b} outside the forecast`,
      leaps: { hidden: 'Hidden component', new: 'New model', instrument: 'Instrument' }, chosen: 'Chosen and sealed',
      answer: (yes) => `Answer: ${yes ? 'yes' : 'no'}`, score: 'log score',
      verdicts: { neptune: 'Neptune', vulcan: 'Vulcan', abstain: 'Abstain' },
      against: (h) => `${h} against the old hypotheses`, againstLens: (h) => `“${h}” against the adopted lens`,
      inN: (n) => `in ${n} measurements`,
      timeMachine: 'Time machine', back: 'Back', next: 'Next', play: 'Play', pause: 'Pause', step: 'Step',
      stepOf: ['step', 'of'], thread: 'The team’s thread',
      chartLabel: (oid) => `Light curve of ${oid} in g and r with the sealed forecasts`, fan: { ia: 'Ia', lens: 'lens' },
    },
    tele: {
      title: 'Forecasts', count: (n) => `${n} bets sealed`, tg: 'SIRA TELEGRAM',
      object: 'Object', model: 'Model', question: 'Question', seal: 'Seal', answer: 'Answer',
      models: { v0: 'v0, physics only', v1: 'v1, Muse team' },
      waiting: (d) => `Waiting for the sky. Answer from ${d}.`, void: 'No measurement to answer it.',
      yes: 'Yes', no: 'No', score: 'log score',
      more: (n) => `SHOW ALL ${n}`, less: 'SHOW 6',
      record: 'LIVE RECORD', answered: 'answered / sealed', right: (r, n) => `${r} of ${n} on the right side of 50%`,
      due: (d) => `Next answers due ${d}`, scored: (n) => (n === 1 ? '1 measurement scored' : `${n} measurements scored`),
      rivals: 'AGAINST ITS RIVALS', rivalsN: (n) => (n === 1 ? 'log score on the same measurement' : `log score on the same ${n} measurements`),
      rivalNames: { sira: 'SIRA', b0: 'Climatology', b1: 'Physics only', b2: 'LLM only' },
      seal2: 'LATEST SEAL', head: 'Head', run: 'Run', check: 'CHECK IT', copy: 'COPY', copied: 'COPIED',
    },
    log: {
      team: 'Replay, full team', solo: 'Replay, Le Verrier', live: 'Live', controls: 'Ia control',
      surprise: 'SURPRISE', proposals: 'PROPOSALS', neptune: 'NEPTUNE ✓', vulcan: 'VULCAN ✗', adopted: 'ADOPTED', abstain: 'ABSTAIN', quiet: 'NO SURPRISE',
      outOf: (a, b) => `${a} of ${b} outside the forecast`, points: (n) => `${n} measurements`,
      joins: 'Joins the lab as a hypothesis', toGrave: 'To the graveyard',
      quietText: 'No forecast missed enough to wake Le Verrier',
      liveText: (s, a) => `No surprises yet: ${s} bets sealed, ${a} answered`,
      ideas: 'WONDER’S PROPOSALS', graveyard: 'GRAVEYARD',
      leaps: { hidden: 'Hidden component', new: 'New model', instrument: 'Instrument' },
      chosen: 'Chosen and sealed', notSealed: 'Not sealed',
    },
    beat: {
      title: 'TODAY’S QUESTIONS', closes: (t) => `CLOSES ${t} CHILE`, q: 'QUESTION', you: 'You', no: 'no', yes: 'yes',
      daysAgo: (n) => `${n} days ago`, today: 'today', sealed: (t) => `Sealed until ${t}`, sira: 'SIRA',
      alias: 'ALIAS', send: (n) => `SEAL MY ${n} BETS`, sent: 'SENT', sending: 'SENDING…',
      sentNote: (t) => `Your bets go into the ledger at ${t}, next to SIRA’s.`, aliasNote: 'Use 2 to 24 letters, numbers, spaces, dots, dashes or underscores.',
      failed: 'Could not send. Try again in a moment.', already: 'You already bet on this round.',
      none: 'The next round opens around midday, Chile time.', offline: 'Bets open once the game’s database is connected.',
      board: 'TABLE', players: (n) => `${n} players`, who: 'Player', resolved: 'Resolved', score: 'Score',
      rows: { sira: 'SIRA', crowd: 'The crowd', sira_crowd: 'SIRA + crowd' },
      last: 'LAST ROUND', siraSaid: 'SIRA said', crowdSaid: 'Crowd', skyAnswer: 'Sky', pending: 'waiting',
      rules: 'RULES',
      ruleList: ['Give a probability from 1 to 99%.', 'Bets close at 18:00 Chile, before night falls at Palomar. Nobody, SIRA included, sees new data before then.', 'The sky answers within days. The score is logarithmic: the more probability you gave to what happened, the better.'],
    },
    live: {
      title: 'INVESTIGATE LIVE', left: (n) => `${n} OF 10 LEFT TODAY`, candidates: 'LAST NIGHT’S CANDIDATES',
      picked: 'LOOKOUTS: YES', passed: 'LOOKOUTS: NO', reader: (label, p) => `READER: ${label === 'real' ? 'REAL' : 'ARTIFACT'} ${p}`,
      betLast: 'BET LAST NIGHT', inRound: 'IN TODAY’S ROUND', investigate: 'INVESTIGATE', starting: 'STARTING…',
      status: { queued: 'WAITING FOR A RUNNER', running: 'THE TEAM IS WORKING', done: 'DONE', failed: 'FAILED' },
      roles: { reader: 'Reader', theorist: 'Theorist', llm_only: 'Muse alone', director: 'Director', senior: 'Senior', forecaster: 'Forecaster', lab: 'Lab' },
      skeptic: (lens) => `${{ instrument: 'Instrument', physics: 'Physics', memory: 'Memory' }[lens] || ''} skeptic`, skeptics: 'Skeptics',
      thinking: 'thinking…', unread: 'could not read the images', callFailed: 'the call failed',
      reads: (label, p) => (label === 'real' ? `sees a real source (${p})` : `sees an artifact (${p} real)`),
      defends: (h) => `defends: ${h}`, artifact: 'calls it an artifact', realSource: 'sees a real source',
      doubts: (hs) => `doubts ${hs.join(', ')}`, noObjection: 'no objection', recognises: 'recognises it', forgets: 'does not recognise it',
      alone: (n) => `forecasts ${n} points on its own`,
      directs: (action) => (action === 'escalate' ? 'asks the senior' : action === 'bet' ? 'picks the question to stake' : 'reviews the bet'),
      words: 'words the bet', dropped: 'The team dropped it: the instrument skeptic called it an artifact.',
      bet: 'SIRA’S BET', classes: 'WHAT IT IS', other: 'Something else',
      chart: (oid) => `Light curve of ${oid} with the team’s forecast`, daysAgo: (n) => `${n} days ago`, now: 'now',
      today: 'TODAY', back: 'BACK TO THE LIST',
      errors: { too_few_points: 'Too few detections to investigate it yet.', in_round: 'It is in today’s Beat SIRA round. Try after 18:00 Chile.', stale: 'The lab did not start this run.', failed: 'The run failed.' },
      refused: {
        sign_in: 'Could not sign in. Try again.', bad_object: 'That is not a ZTF object.', not_connected: 'The live lab is not connected yet.',
        in_round: 'It is in today’s Beat SIRA round. Try after 18:00 Chile.', busy: 'Your investigation is still running.',
        daily_limit: 'The lab has done its 10 investigations for today. More from 21:00 Chile.', budget: 'The lab has spent today’s budget. More from 21:00 Chile.',
        error: 'Could not start. Try again in a moment.',
      },
      offline: 'The live lab opens once its database is connected.',
      how: 'HOW IT WORKS',
      howList: ['The team that bets every night investigates the object you pick: reader, theorists, skeptics, director and forecaster.', 'A run takes 2 to 3 minutes and costs about US$0.10. The lab does 10 a day.', 'These runs stay out of the official ledger, so visitors cannot steer SIRA’s record.', 'Objects in today’s Beat SIRA round open after the bell.'],
    },
  },
  es: {
    tagline: 'Una IA astrónoma hecha para que la refuten en público',
    tabs: { lab: 'Laboratorio', live: 'Investigar', beat: 'Apuesta contra SIRA', telegrams: 'Pronósticos', logbook: 'Bitácora' },
    sections: 'Secciones', language: 'Idioma', theme: 'Tema', themes: { dark: 'Oscuro', light: 'Claro' },
    repo: 'Código', ledger: 'Registro público', protocol: 'Protocolo', loading: 'Cargando…',
    credits: 'Imágenes: Pan-STARRS1 a través del visor de Legacy Surveys; Legacy Surveys / D. Lang (Perimeter Institute), CC BY 4.0; ZTF a través de ALeRCE.',
    fig: { days: 'días', now: 'ahora' },
    thread: { more: 'Más abajo' },
    dome: {
      label: 'Corte del observatorio de SIRA: el telescopio bajo la cúpula, el laboratorio y la sala de control, con el equipo trabajando',
      names: {
        vig: 'Vigías', lec: 'Lector', ein: 'Escéptico de instrumento', efi: 'Escéptico de física', eme: 'Escéptico de memoria', muse: 'Muse sola',
        dir: 'Director', sen: 'Senior', pro: 'Pronosticador', lv: 'Le Verrier', ztf: 'ZTF',
      },
      hyp: { ia: 'Ia', ibc: 'Ibc', ii: 'II', tde: 'TDE', adopted: 'la lente' },
      theorist: (h) => (h === 'adopted' ? 'Teórico de la lente' : `Teórico ${h}`),
      seconds: (n) => `${n}\u00a0s`,
      reads: (real, p) => (real ? `Ve una fuente real (${p}).` : `¿Una resta fallida? ${p} real.`),
      defends: (h) => `Defiende ${h}.`, realSource: 'Ve una fuente real.', artifact: 'Es un artefacto.',
      doubts: (hs) => `Duda de ${hs.length > 1 ? `${hs.slice(0, -1).join(', ')} ${/^I/.test(hs[hs.length - 1]) ? 'e' : 'y'} ${hs[hs.length - 1]}` : hs[0]}.`,
      noObjection: 'Sin objeciones.', recognises: 'Lo reconoce.', forgets: 'No lo reconoce.',
      alone: (n) => `Pronostica ${n} puntos por su cuenta.`,
      directs: (action) => (action === 'escalate' ? 'Consulta al senior.' : action === 'bet' ? 'Elige la pregunta de la apuesta.' : 'Revisa la apuesta.'),
      words: 'Redacta la apuesta.', proposes: (name) => `Propone «${name}».`,
    },
    lab: {
      names: { dome: 'Lector', theory: 'Teóricos', skeptics: 'Escépticos', forecaster: 'Pronosticador', director: 'Director', leverrier: 'Le Verrier', sky: 'El cielo' },
      marks: { dome: 'L', theory: 'T', skeptics: 'E', forecaster: 'P', director: 'D', leverrier: 'LV', sky: 'ZTF' },
      panels: ['ciencia', 'referencia', 'diferencia', 'zoom ×3'],
      stampsAlt: (oid) => `Primeras imágenes de ZTF de ${oid}: ciencia, referencia, diferencia y zoom`,
      skyAlt: (oid) => `Campo de Pan-STARRS1 alrededor de ${oid}`, first: 'primera detección',
      hyp: { ia: 'Supernova tipo Ia', ibc: 'Supernova tipo Ibc', ii: 'Supernova tipo II', tde: 'Disrupción por marea', null: 'Ninguna de las anteriores', adopted: 'Lente invisible' },
      lenses: { instrument: 'Escéptico de instrumento', physics: 'Escéptico de física', memory: 'Escéptico de memoria' },
      realSource: 've una fuente real', artifact: 'lo llama artefacto', doubts: (hs) => `duda de ${hs.join(', ')}`,
      recognises: 'lo reconoce', forgets: 'no lo reconoce',
      choices: { wait: 'Esperar', think: 'Pensar', escalate: 'Escalar', ask: 'Preguntar' },
      measurements: (n) => `${n} mediciones`, outside: (a, b) => `${a} de ${b} fuera del pronóstico`,
      leaps: { hidden: 'Componente oculto', new: 'Modelo nuevo', instrument: 'Instrumento' }, chosen: 'Elegida y sellada',
      answer: (yes) => `Respuesta: ${yes ? 'sí' : 'no'}`, score: 'puntaje log',
      verdicts: { neptune: 'Neptuno', vulcan: 'Vulcano', abstain: 'Abstención' },
      against: (h) => `${h} contra las hipótesis viejas`, againstLens: (h) => `«${h}» contra la lente adoptada`,
      inN: (n) => `en ${n} mediciones`,
      timeMachine: 'Máquina del tiempo', back: 'Atrás', next: 'Siguiente', play: 'Reproducir', pause: 'Pausa', step: 'Paso',
      stepOf: ['paso', 'de'], thread: 'Conversación del equipo',
      chartLabel: (oid) => `Curva de luz de ${oid} en g y r con los pronósticos sellados`, fan: { ia: 'Ia', lens: 'lente' },
    },
    tele: {
      title: 'Pronósticos', count: (n) => `${n} apuestas selladas`, tg: 'TELEGRAMA SIRA',
      object: 'Objeto', model: 'Modelo', question: 'Pregunta', seal: 'Sello', answer: 'Respuesta',
      models: { v0: 'v0, solo física', v1: 'v1, equipo Muse' },
      waiting: (d) => `Esperando al cielo. Respuesta desde el ${d}.`, void: 'Sin medición para responderla.',
      yes: 'Sí', no: 'No', score: 'puntaje log',
      more: (n) => `VER LAS ${n}`, less: 'VER 6',
      record: 'RÉCORD EN VIVO', answered: 'respondidas / selladas', right: (r, n) => `${r} de ${n} del lado correcto del 50 %`,
      due: (d) => `Próximas respuestas el ${d}`, scored: (n) => (n === 1 ? '1 medición puntuada' : `${n} mediciones puntuadas`),
      rivals: 'CONTRA SUS RIVALES', rivalsN: (n) => (n === 1 ? 'puntaje log en la misma medición' : `puntaje log en las mismas ${n} mediciones`),
      rivalNames: { sira: 'SIRA', b0: 'Climatología', b1: 'Solo física', b2: 'Solo LLM' },
      seal2: 'ÚLTIMO SELLO', head: 'Cabeza', run: 'Corrida', check: 'VERIFÍCALO', copy: 'COPIAR', copied: 'COPIADO',
    },
    log: {
      team: 'Replay, equipo completo', solo: 'Replay, Le Verrier', live: 'En vivo', controls: 'Ia de control',
      surprise: 'SORPRESA', proposals: 'PROPUESTAS', neptune: 'NEPTUNO ✓', vulcan: 'VULCANO ✗', adopted: 'ADOPTADA', abstain: 'ABSTENCIÓN', quiet: 'SIN SORPRESA',
      outOf: (a, b) => `${a} de ${b} fuera del pronóstico`, points: (n) => `${n} mediciones`,
      joins: 'Entra al lab como hipótesis', toGrave: 'Al cementerio',
      quietText: 'Ningún pronóstico falló lo suficiente para despertar a Le Verrier',
      liveText: (s, a) => `Sin sorpresas todavía: ${s} apuestas selladas, ${a} respondidas`,
      ideas: 'PROPUESTAS DE WONDER', graveyard: 'CEMENTERIO',
      leaps: { hidden: 'Componente oculto', new: 'Modelo nuevo', instrument: 'Instrumento' },
      chosen: 'Elegida y sellada', notSealed: 'No sellada',
    },
    beat: {
      title: 'PREGUNTAS DE HOY', closes: (t) => `CIERRA ${t} CHILE`, q: 'PREGUNTA', you: 'Tú', no: 'no', yes: 'sí',
      daysAgo: (n) => `hace ${n} días`, today: 'hoy', sealed: (t) => `Sellada hasta las ${t}`, sira: 'SIRA',
      alias: 'ALIAS', send: (n) => `SELLAR MIS ${n} APUESTAS`, sent: 'ENVIADAS', sending: 'ENVIANDO…',
      sentNote: (t) => `Tus apuestas entran a la bitácora a las ${t}, junto a las de SIRA.`, aliasNote: 'Usa de 2 a 24 letras, números, espacios, puntos o guiones.',
      failed: 'No se pudo enviar. Prueba de nuevo en un momento.', already: 'Ya apostaste en esta ronda.',
      none: 'La próxima ronda abre cerca del mediodía de Chile.', offline: 'Las apuestas abren cuando la base de datos del juego esté conectada.',
      board: 'TABLA', players: (n) => `${n} jugadores`, who: 'Jugador', resolved: 'Resueltas', score: 'Puntaje',
      rows: { sira: 'SIRA', crowd: 'La multitud', sira_crowd: 'SIRA + multitud' },
      last: 'ÚLTIMA RONDA', siraSaid: 'SIRA dijo', crowdSaid: 'Multitud', skyAnswer: 'Cielo', pending: 'esperando',
      rules: 'REGLAS',
      ruleList: ['Da una probabilidad de 1 a 99 %.', 'Las apuestas cierran a las 18:00 de Chile, antes de que anochezca en Palomar. Nadie, ni SIRA, ve datos nuevos antes.', 'El cielo responde en pocos días. El puntaje es logarítmico: mientras más probabilidad le diste a lo que pasó, mejor.'],
    },
    live: {
      title: 'INVESTIGAR EN VIVO', left: (n) => `QUEDAN ${n} DE 10 HOY`, candidates: 'CANDIDATOS DE ANOCHE',
      picked: 'VIGÍAS: SÍ', passed: 'VIGÍAS: NO', reader: (label, p) => `LECTOR: ${label === 'real' ? 'REAL' : 'ARTEFACTO'} ${p}`,
      betLast: 'APOSTÓ ANOCHE', inRound: 'EN LA RONDA DE HOY', investigate: 'INVESTIGAR', starting: 'INICIANDO…',
      status: { queued: 'ESPERANDO UN SERVIDOR', running: 'EL EQUIPO ESTÁ TRABAJANDO', done: 'LISTO', failed: 'FALLÓ' },
      roles: { reader: 'Lector', theorist: 'Teórico', llm_only: 'Muse sola', director: 'Director', senior: 'Senior', forecaster: 'Pronosticador', lab: 'Laboratorio' },
      skeptic: (lens) => `Escéptico de ${{ instrument: 'instrumento', physics: 'física', memory: 'memoria' }[lens] || ''}`, skeptics: 'Escépticos',
      thinking: 'pensando…', unread: 'no pudo leer las imágenes', callFailed: 'la llamada falló',
      reads: (label, p) => (label === 'real' ? `ve una fuente real (${p})` : `ve un artefacto (${p} real)`),
      defends: (h) => `defiende: ${h}`, artifact: 'lo llama artefacto', realSource: 've una fuente real',
      doubts: (hs) => `duda de ${hs.join(', ')}`, noObjection: 'sin objeciones', recognises: 'lo reconoce', forgets: 'no lo reconoce',
      alone: (n) => `pronostica ${n} puntos por su cuenta`,
      directs: (action) => (action === 'escalate' ? 'consulta al senior' : action === 'bet' ? 'elige la pregunta de la apuesta' : 'revisa la apuesta'),
      words: 'redacta la apuesta', dropped: 'El equipo lo descartó: el escéptico de instrumento lo llamó artefacto.',
      bet: 'LA APUESTA DE SIRA', classes: 'QUÉ ES', other: 'Otra cosa',
      chart: (oid) => `Curva de luz de ${oid} con el pronóstico del equipo`, daysAgo: (n) => `hace ${n} días`, now: 'ahora',
      today: 'HOY', back: 'VOLVER A LA LISTA',
      errors: { too_few_points: 'Todavía tiene muy pocas detecciones para investigarlo.', in_round: 'Está en la ronda de hoy de Apuesta contra SIRA. Prueba después de las 18:00 de Chile.', stale: 'El laboratorio no inició esta corrida.', failed: 'La corrida falló.' },
      refused: {
        sign_in: 'No se pudo iniciar sesión. Prueba de nuevo.', bad_object: 'Ese no es un objeto de ZTF.', not_connected: 'El laboratorio en vivo todavía no está conectado.',
        in_round: 'Está en la ronda de hoy de Apuesta contra SIRA. Prueba después de las 18:00 de Chile.', busy: 'Tu investigación todavía está corriendo.',
        daily_limit: 'El laboratorio ya hizo sus 10 investigaciones de hoy. Vuelve desde las 21:00 de Chile.', budget: 'El laboratorio ya gastó el presupuesto de hoy. Vuelve desde las 21:00 de Chile.',
        error: 'No se pudo iniciar. Prueba de nuevo en un momento.',
      },
      offline: 'El laboratorio en vivo abre cuando su base de datos esté conectada.',
      how: 'CÓMO FUNCIONA',
      howList: ['El equipo que apuesta cada noche investiga el objeto que elijas: lector, teóricos, escépticos, director y pronosticador.', 'Cada corrida tarda de 2 a 3 minutos y cuesta unos US$ 0,10. El laboratorio hace 10 al día.', 'Estas corridas quedan fuera de la bitácora oficial, para que los visitantes no puedan torcer el récord de SIRA.', 'Los objetos de la ronda de hoy de Apuesta contra SIRA se abren después de la campana.'],
    },
  },
};
