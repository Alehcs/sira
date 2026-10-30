import { useEffect, useState } from 'react';
import Beat from './Beat.jsx';
import Investigate from './Investigate.jsx';
import Lab from './Lab.jsx';
import Logbook from './Logbook.jsx';
import Telegrams from './Telegrams.jsx';
import { WORDS } from './words.js';

const TABS = ['lab', 'live', 'beat', 'telegrams', 'logbook'];
const fromHash = () => (TABS.includes(window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'lab');

function firstLang() {
  try {
    const saved = localStorage.getItem('lang');
    if (saved === 'en' || saved === 'es') return saved;
  } catch (e) { /* storage can be blocked */ }
  return (navigator.language || '').toLowerCase().startsWith('es') ? 'es' : 'en';
}

function useJson(path) {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch(import.meta.env.BASE_URL + path).then((r) => (r.ok ? r.json() : null)).then(setData).catch(() => setData(null));
  }, [path]);
  return data;
}

export default function App() {
  const [lang, setLang] = useState(firstLang);
  const [tab, setTab] = useState(fromHash);
  const live = useJson('data/live.json');
  const lab = useJson('replays/lab.json');
  const book = useJson('replays/logbook.json');
  const w = WORDS[lang];

  useEffect(() => {
    const follow = () => setTab(fromHash());
    window.addEventListener('hashchange', follow);
    return () => window.removeEventListener('hashchange', follow);
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    try { localStorage.setItem('lang', lang); } catch (e) { /* storage can be blocked */ }
  }, [lang]);

  return (
    <div className="page">
      <header className="top">
        <div className="brand"><h1>SIRA LAB</h1><span>{w.tagline}</span></div>
        <div className="controls">
          <nav className="tabs" aria-label={w.sections}>
            {TABS.map((t) => <a key={t} href={`#${t}`} aria-current={tab === t ? 'page' : undefined}>{w.tabs[t]}</a>)}
          </nav>
          <div className="langs" role="group" aria-label={w.language}>
            {['en', 'es'].map((l) => <button key={l} type="button" aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}
          </div>
        </div>
      </header>
      <main>
        {tab === 'lab' && (lab ? <Lab lang={lang} data={lab} /> : <p className="muted">{w.loading}</p>)}
        {tab === 'live' && <Investigate lang={lang} live={live} />}
        {tab === 'beat' && <Beat lang={lang} live={live} />}
        {tab === 'telegrams' && (live ? <Telegrams lang={lang} live={live} /> : <p className="muted">{w.loading}</p>)}
        {tab === 'logbook' && (book ? <Logbook lang={lang} lanes={book} live={live} /> : <p className="muted">{w.loading}</p>)}
      </main>
      <footer>
        <a href="https://github.com/Alehcs/sira">{w.repo}</a>
        <a href="https://github.com/Alehcs/sira/tree/ledger">{w.ledger}</a>
        <a href="https://github.com/Alehcs/sira#the-protocol">{w.protocol}</a>
      </footer>
    </div>
  );
}
