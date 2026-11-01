import { WORDS, format } from './words.js';
import './hero.css';

const BASE = import.meta.env.BASE_URL;

// the Lab's opening: what SIRA does, its pre-registered numbers and the loop, over the real sky of the featured case
export default function Hero({ lang, proof, onWatch }) {
  const w = WORDS[lang].hero;
  const f = format(lang);
  const times = (v) => {
    const x = Math.exp(Math.round(v * 100) / 100);
    return `${f.num(x, x >= 2 ? 1 : 2)}×`;
  };
  const figs = [
    [times(proof.vs_muse), w.figs.muse(proof.objects)],
    [times(proof.vs_physics), w.figs.physics],
    [w.outOf(proof.lens_wins, proof.surprises), w.figs.lens],
    [f.money(proof.usd), w.figs.usd],
  ];
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="backdrop" aria-hidden="true">
        <div className="field"><img src={`${BASE}replays/sky.jpg`} alt="" /></div>
      </div>
      <div className="wrap inner">
        <h1 id="hero-title">{w.title}</h1>
        <p className="what">{w.what}</p>
        <div className="actions">
          <button type="button" className="hbtn primary" onClick={onWatch}>{w.watch}</button>
          <a className="hbtn" href="#beat">{w.play}</a>
        </div>
        <dl className="figs">
          {figs.map(([big, small]) => <div key={small}><dt>{big}</dt><dd>{small}</dd></div>)}
        </dl>
        <a className="claims" href="https://github.com/Alehcs/sira/blob/main/CLAIMS.md">{w.claims}</a>
        <ol className="loop">
          {w.loop.map(([name, model, kind, text]) => (
            <li key={name}><p className="step"><b>{name}</b><span className={`model ${kind}`}>{model}</span></p><p>{text}</p></li>
          ))}
        </ol>
      </div>
    </section>
  );
}
