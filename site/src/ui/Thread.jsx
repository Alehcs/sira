import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WORDS } from '../words.js';

// the agents' messages, oldest first, in their own scroll box kept on the message of the current step
export function Thread({ lang, label, current, children }) {
  const box = useRef(null);
  const pinned = useRef(true);
  const target = useRef(null);
  const [below, setBelow] = useState(false);
  const look = () => {
    const el = box.current;
    if (el) setBelow(el.scrollTop + el.clientHeight < el.scrollHeight - 8);
  };
  const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const pin = (smooth) => {
    const el = box.current;
    const mine = el.querySelector('[aria-current="step"]');
    if (!mine) return;
    const top = Math.min(mine.offsetTop, el.scrollHeight - el.clientHeight);
    if (target.current !== null && !smooth && Math.abs(top - target.current) < 2) return;
    target.current = top;
    el.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' });
  };

  useEffect(() => {
    const el = box.current;
    // fonts and widths change the messages' heights: until the reader scrolls, follow the current one
    const watch = new ResizeObserver(() => { if (pinned.current) pin(false); look(); });
    watch.observe(el);
    watch.observe(el.firstElementChild);
    const free = () => { pinned.current = false; };
    const events = ['wheel', 'touchstart', 'keydown', 'pointerdown'];
    events.forEach((e) => el.addEventListener(e, free, { passive: true }));
    return () => { watch.disconnect(); events.forEach((e) => el.removeEventListener(e, free)); };
  }, []);
  useLayoutEffect(() => {
    const smooth = target.current !== null && !calm();
    pinned.current = true;
    target.current = smooth ? target.current : null;
    pin(smooth);
    look();
  }, [current]);

  const more = WORDS[lang].thread.more;
  const down = () => {
    pinned.current = false;
    box.current.scrollBy({ top: box.current.clientHeight * 0.8, behavior: calm() ? 'auto' : 'smooth' });
  };
  return (
    <div className="thread">
      <div className="thread-scroll" ref={box} tabIndex={0} role="region" aria-label={label} onScroll={look}>
        <ol>{children}</ol>
      </div>
      {below && <button type="button" className="more" aria-label={more} title={more} onClick={down}>↓</button>}
    </div>
  );
}

// one agent speaking: monogram, role, model, when, spend, its sentence, its own words and what it attaches
export function Message({ mark, name, model, when, at, cost, says, text, quote, current, children }) {
  return (
    <li className="msg" aria-current={current ? 'step' : undefined}>
      <span className={`monogram${mark.length > 2 ? ' three' : ''}`} aria-hidden="true">{mark}</span>
      <div>
        <div className="byline">
          <b>{name}</b>
          {model && <span>{model}</span>}
          {when && <time dateTime={at}>{when}</time>}
          {cost && <span>{cost}</span>}
        </div>
        {says && <p className="says">{says}</p>}
        {text && <p className="story">{text}</p>}
        {quote && <p className="quote" lang={quote.lang}><q>{quote.text}</q></p>}
        {children && <div className="att">{children}</div>}
      </div>
    </li>
  );
}
