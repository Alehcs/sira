import { useEffect, useState } from 'react';
import Archive from './Archive.jsx';
import Beat from './Beat.jsx';
import Investigate from './Investigate.jsx';
import Lab from './Lab.jsx';
import Logbook from './Logbook.jsx';
import Telegrams from './Telegrams.jsx';
import { WORDS } from './words.js';

const TABS = ['lab', 'live', 'archive', 'beat', 'telegrams', 'logbook'];
const fromHash = () => (TABS.includes(window.location.hash.slice(1).split('/')[0]) ? window.location.hash.slice(1).split('/')[0] : 'lab');

function firstLang() {
  try {
    const saved = localStorage.getItem('lang');
    if (saved === 'en' || saved === 'es') return saved;
  } catch (e) { /* storage can be blocked */ }
  return (navigator.language || '').toLowerCase().startsWith('es') ? 'es' : 'en';
}

function firstTheme() {
  try {
    if (localStorage.getItem('theme') === 'dark') return 'dark';
  } catch (e) { /* storage can be blocked */ }
  return 'light';
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
  const [theme, setTheme] = useState(firstTheme);
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
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch (e) { /* storage can be blocked */ }
  }, [theme]);

  return (
    <>
      <header className="site wrap">
        <p className="brand"><b>SIRA</b><span>{w.tagline}</span></p>
        <nav className="tabs" aria-label={w.sections}>
          {TABS.map((t) => <a key={t} href={`#${t}`} aria-current={tab === t ? 'page' : undefined}>{w.tabs[t]}</a>)}
        </nav>
        <div className="switches">
          <div className="seg" role="group" aria-label={w.language}>
            {['en', 'es'].map((l) => <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}
          </div>
          <div className="seg" role="group" aria-label={w.theme}>
            {['dark', 'light'].map((t) => <button key={t} type="button" aria-pressed={theme === t} onClick={() => setTheme(t)}>{w.themes[t]}</button>)}
          </div>
        </div>
      </header>
      <main className="wrap">
        {tab === 'lab' && (lab ? <Lab lang={lang} data={lab} /> : <p className="muted">{w.loading}</p>)}
        {tab === 'live' && <Investigate lang={lang} live={live} />}
        {tab === 'archive' && <Archive lang={lang} live={live} />}
        {tab === 'beat' && <Beat lang={lang} live={live} />}
        {tab === 'telegrams' && (live ? <Telegrams lang={lang} live={live} /> : <p className="muted">{w.loading}</p>)}
        {tab === 'logbook' && (book ? <Logbook lang={lang} lanes={book} live={live} /> : <p className="muted">{w.loading}</p>)}
      </main>
      <footer className="wrap">
        <div className="foot">
          <div className="links">
            <a href="https://github.com/Alehcs/sira">{w.repo}</a>
            <a href="https://github.com/Alehcs/sira/tree/ledger">{w.ledger}</a>
            <a href="https://github.com/Alehcs/sira#the-protocol">{w.protocol}</a>
          </div>
          <p>{w.credits}</p>
        </div>
      </footer>
    </>
  );
}
