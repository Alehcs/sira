import { useEffect, useState } from 'react';
import Archive from './Archive.jsx';
import Beat from './Beat.jsx';
import Investigate from './Investigate.jsx';
import Hero from './Hero.jsx';
import Lab from './Lab.jsx';
import Logbook from './Logbook.jsx';
import Telegrams from './Telegrams.jsx';
import { Credit } from './ui/Photos.jsx';
import { WORDS } from './words.js';

const TABS = ['lab', 'live', 'archive', 'beat', 'telegrams', 'logbook'];
const fromHash = () => (TABS.includes(window.location.hash.slice(1).split('/')[0]) ? window.location.hash.slice(1).split('/')[0] : 'lab');

// a sun for light, a moon for dark
const ICONS = {
  light: (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <circle cx="9" cy="9" r="3.4" />
      <path d="M9 1.5v2M9 14.5v2M1.5 9h2M14.5 9h2M3.7 3.7l1.4 1.4M12.9 12.9l1.4 1.4M3.7 14.3l1.4-1.4M12.9 5.1l1.4-1.4" />
    </svg>
  ),
  dark: (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round">
      <path d="M14.8 11.2A6.2 6.2 0 0 1 6.8 3.2a6.2 6.2 0 1 0 8 8z" />
    </svg>
  ),
};

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
  const [labView, setLabView] = useState(null);
  const live = useJson('data/live.json');
  const lab = useJson('replays/lab.json');
  const book = useJson('replays/logbook.json');
  const w = WORDS[lang];

  // the opening band's button: the featured case, scrolled into view once it is on the page
  const watch = () => {
    setLabView('featured');
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    requestAnimationFrame(() => {
      const el = document.getElementById('case');
      if (el) el.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
    });
  };

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
            {['light', 'dark'].map((t) => (
              <button key={t} type="button" className="icon" aria-pressed={theme === t} aria-label={w.themes[t]} title={w.themes[t]} onClick={() => setTheme(t)}>{ICONS[t]}</button>
            ))}
          </div>
        </div>
      </header>
      {tab === 'lab' && live && live.proof && <Hero lang={lang} proof={live.proof} onWatch={watch} />}
      <main className="wrap">
        {tab === 'lab' && (lab ? <Lab lang={lang} data={lab} view={labView} setView={setLabView} /> : <p className="muted">{w.loading}</p>)}
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
          <p>{w.built}</p>
          <p>{w.credits.images}: <Credit />; {w.credits.ps1}; {w.credits.ztf}.</p>
        </div>
      </footer>
    </>
  );
}
