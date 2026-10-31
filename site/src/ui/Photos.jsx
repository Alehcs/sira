import { useWidth } from './width.js';

// two thin ticks pointing at the centre, from the left and from above, never over the object
function Ticks({ side }) {
  const c = side / 2;
  const gap = Math.max(5, Math.round(side * 0.05));
  const len = Math.max(9, Math.round(side * 0.11));
  const d = `M${c - gap - len} ${c}H${c - gap}M${c} ${c - gap - len}V${c - gap}`;
  return (
    <svg className="ticks" width={side} height={side} aria-hidden="true">
      <path className="halo" d={d} /><path className="tk" d={d} />
    </svg>
  );
}

function Shot({ src, size, at, side, k, label, host }) {
  const style = host
    ? { width: side, height: side, backgroundImage: `url(${src})`, backgroundSize: `${side}px ${side}px` }
    : { width: side, height: side, backgroundImage: `url(${src})`, backgroundSize: `${size[0] * k}px ${size[1] * k}px`, backgroundPosition: `${-at * (size[0] / 3) * k}px 0` };
  return (
    <figure className="shot" style={{ width: side }}>
      <div className="pic"><i role="img" aria-label={label} style={style} /><Ticks side={side} /></div>
      <figcaption aria-hidden="true">{label}</figcaption>
    </figure>
  );
}

// the three ZTF images at one whole scale, in a row when they fit and one under another on phones, then the colour image of the field
export default function Photos({ src, panel, host, labels, alt }) {
  const [ref, W] = useWidth();
  const p = panel[0];
  const gap = 12;
  const fits = Math.floor((W - 2 * gap) / (3 * p));
  const row = fits >= 2;
  const k = Math.max(1, Math.min(3, row ? fits : Math.floor(W / p)));
  const hostScale = W >= 256 ? 2 : 1;
  const size = [p * 3, panel[1]];
  return (
    <div className="photos" ref={ref} role="group" aria-label={alt}>
      {W > 0 && (
        <>
          <div className={`ztf${row ? ' row' : ''}`}>
            {[0, 1, 2].map((at) => <Shot key={at} src={src} size={size} at={at} side={p * k} k={k} label={labels[at]} />)}
          </div>
          {host && <Shot src={host} side={128 * hostScale} label={labels[3]} host />}
        </>
      )}
    </div>
  );
}
