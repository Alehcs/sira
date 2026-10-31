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

// the ZTF science image large, the reference and the difference beside it, and the colour image of the field, all at whole scales
export default function Photos({ src, panel, host, labels, alt }) {
  const [ref, W] = useWidth();
  const p = panel[0];
  const big = Math.max(1, Math.min(5, Math.floor(W / p)));
  const small = Math.max(1, Math.min(2, Math.floor((W - 12) / (2 * p))));
  const hostScale = W >= 256 ? 2 : 1;
  // the reference and difference stand beside the main photo when there is room, else in a row under it
  const beside = W >= p * big + 12 + p * small;
  const size = [p * 3, panel[1]];
  return (
    <div className="photos" ref={ref} role="group" aria-label={alt}>
      {W > 0 && (
        <>
          <Shot src={src} size={size} at={0} side={p * big} k={big} label={labels[0]} />
          <div className={`pair${beside ? ' beside' : ''}`}>
            <Shot src={src} size={size} at={1} side={p * small} k={small} label={labels[1]} />
            <Shot src={src} size={size} at={2} side={p * small} k={small} label={labels[2]} />
          </div>
          {host && <Shot src={host} side={128 * hostScale} label={labels[3]} host />}
        </>
      )}
    </div>
  );
}
