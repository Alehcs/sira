import { useWidth } from './width.js';

// a colour field in its own pixels with finder ticks, the ZTF stamp's box, a 1′ bar and the position
export default function Sky({ src, size, at, scale, box = 63, coords, label }) {
  const [ref, W] = useWidth();
  const k = W && W < 600 ? 2 : 1; // phones see twice the field at half the size
  const H = k > 1 ? 200 : 320;
  const [cx, cy] = at;
  const vw = W * k;
  const vh = H * k;
  const x0 = Math.max(0, Math.min(cx - vw / 2, size[0] - vw));
  const y0 = Math.max(0, Math.min(cy - vh / 2, size[1] - vh));
  const s = (v) => v * k;
  const side = box / scale;
  const arcmin = 60 / scale;
  const ticks = `M${cx - s(40)} ${cy}H${cx - s(13)}M${cx} ${cy - s(40)}V${cy - s(13)}`;
  const square = `M${cx - side / 2} ${cy - side / 2}h${side}v${side}h-${side}z`;
  const bx = x0 + s(24);
  const by = y0 + vh - s(22);
  const bar = `M${bx} ${by - s(5)}v${s(10)}M${bx} ${by}h${arcmin}M${bx + arcmin} ${by - s(5)}v${s(10)}`;
  const type = { fontSize: s(13), strokeWidth: s(3) };
  return (
    <div className="sky" ref={ref} style={{ height: H }}>
      {W > 0 && (
        <svg viewBox={`${x0} ${y0} ${vw} ${vh}`} preserveAspectRatio="xMidYMid slice" role="img" aria-label={label}>
          <image href={src} x="0" y="0" width={size[0]} height={size[1]} />
          {['halo', 'tk'].map((c) => (
            <g key={c} className={c}>
              <path d={ticks} /><path d={square} strokeDasharray={`${s(6)} ${s(5)}`} /><path d={bar} />
            </g>
          ))}
          <text x={bx + arcmin / 2} y={by - s(10)} textAnchor="middle" {...type}>1′</text>
          <text x={cx + side / 2} y={cy - side / 2 - s(8)} textAnchor="end" {...type}>{box}″</text>
          {k > 1
            ? <text x={x0 + s(12)} y={y0 + s(22)} fontSize={s(12)} strokeWidth={s(3)}>{coords}</text>
            : <text x={cx - side / 2} y={cy + side / 2 + s(19)} {...type}>{coords}</text>}
        </svg>
      )}
    </div>
  );
}
