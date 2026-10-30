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
  const pct = (p) => {
    const n = Math.round(p * 1000) / 10;
    const s = decimal(Number.isInteger(n) ? String(n) : n.toFixed(1));
    return es ? `${s} %` : `${s}%`;
  };
  const money = (v) => (es ? `US$ ${decimal(v.toFixed(2))}` : `US$${v.toFixed(2)}`);
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
  return { num, pct, money, day, short, stamp, chile, term, name, question };
}

export const WORDS = {
  en: {
    tagline: 'An AI astronomer built to be proven wrong in public',
    tabs: { lab: 'LAB', beat: 'BEAT SIRA', telegrams: 'TELEGRAMS', logbook: 'LOGBOOK' },
    sections: 'Sections', language: 'Language', repo: 'Code', ledger: 'Ledger', protocol: 'Protocol', loading: 'Loading…',
    lab: {
      dome: 'OBSERVATION DOME', theory: 'THEORY ROOM', skeptics: 'SKEPTICS BENCH', forecaster: 'FORECAST DESK',
      director: 'DIRECTOR’S OFFICE', leverrier: 'LE VERRIER’S BOARD', sky: 'WINDOW TO THE SKY',
      panels: ['science', 'reference', 'difference', 'zoom ×3'], real: (p) => `${p} real`,
      stampsAlt: (oid) => `First ZTF images of ${oid}: science, reference, difference and zoom`,
      lenses: ['instrument', 'physics', 'memory'], asleep: 'Asleep',
      hyp: { ia: 'Type Ia supernova', ibc: 'Type Ibc supernova', ii: 'Type II supernova', tde: 'Tidal disruption', null: 'None of the above', adopted: 'Invisible lens' },
      choices: ['WAIT', 'THINK', 'ESCALATE', 'ASK'], measurements: (n) => `${n} measurements`,
      neptune: 'NEPTUNE ✓', abstain: 'ABSTAIN', secondIdea: 'Le Verrier’s 2nd idea',
      timeMachine: 'TIME MACHINE', back: 'Back', next: 'Next', play: 'Play', pause: 'Pause', step: 'Step',
      chartLabel: (oid) => `Light curve of ${oid} in r with the sealed forecasts`, brightness: 'brightness', now: 'now',
      fan: { ia: 'Ia', lens: 'lens' }, log: 'LOG',
      names: { dome: 'Reader', theory: 'Theorists', skeptics: 'Skeptics', forecaster: 'Forecaster', director: 'Director', leverrier: 'Le Verrier', sky: 'The Sky' },
    },
    tele: {
      title: 'TELEGRAMS', count: (n) => `${n} bets sealed`, tg: 'SIRA TELEGRAM',
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
  },
  es: {
    tagline: 'Una IA astrónoma hecha para que la refuten en público',
    tabs: { lab: 'LABORATORIO', beat: 'APUESTA CONTRA SIRA', telegrams: 'TELEGRAMAS', logbook: 'BITÁCORA' },
    sections: 'Secciones', language: 'Idioma', repo: 'Código', ledger: 'Bitácora pública', protocol: 'Protocolo', loading: 'Cargando…',
    lab: {
      dome: 'CÚPULA DE OBSERVACIÓN', theory: 'SALA DE TEORÍA', skeptics: 'BANCO DE ESCÉPTICOS', forecaster: 'MESA DEL PRONOSTICADOR',
      director: 'OFICINA DEL DIRECTOR', leverrier: 'PIZARRA DE LE VERRIER', sky: 'VENTANA AL CIELO',
      panels: ['ciencia', 'referencia', 'diferencia', 'zoom ×3'], real: (p) => `${p} real`,
      stampsAlt: (oid) => `Primeras imágenes de ZTF de ${oid}: ciencia, referencia, diferencia y zoom`,
      lenses: ['instrumento', 'física', 'memoria'], asleep: 'Dormido',
      hyp: { ia: 'Supernova tipo Ia', ibc: 'Supernova tipo Ibc', ii: 'Supernova tipo II', tde: 'Disrupción por marea', null: 'Ninguna de las anteriores', adopted: 'Lente invisible' },
      choices: ['ESPERAR', 'PENSAR', 'ESCALAR', 'PREGUNTAR'], measurements: (n) => `${n} mediciones`,
      neptune: 'NEPTUNO ✓', abstain: 'ABSTENCIÓN', secondIdea: '2.ª idea de Le Verrier',
      timeMachine: 'MÁQUINA DEL TIEMPO', back: 'Atrás', next: 'Siguiente', play: 'Reproducir', pause: 'Pausa', step: 'Paso',
      chartLabel: (oid) => `Curva de luz de ${oid} en r con los pronósticos sellados`, brightness: 'brillo', now: 'ahora',
      fan: { ia: 'Ia', lens: 'lente' }, log: 'REGISTRO',
      names: { dome: 'Lector', theory: 'Teóricos', skeptics: 'Escépticos', forecaster: 'Pronosticador', director: 'Director', leverrier: 'Le Verrier', sky: 'El Cielo' },
    },
    tele: {
      title: 'TELEGRAMAS', count: (n) => `${n} apuestas selladas`, tg: 'TELEGRAMA SIRA',
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
  },
};
