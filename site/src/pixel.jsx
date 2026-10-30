// pixel sprite: H hat, S skin, E eyes, C coat, A accent, L legs
const SPRITE = ['...HHHH...', '..HHHHHH..', '..HSSSSH..', '..SESSES..', '..SSSSSS..', '...SSSS...', '..CCCCCC..', '.CCCAACCC.', '.SCCAACCS.', '..CCCCCC..', '..LL..LL..', '..LL..LL..'];
const layer = (ch) => SPRITE.flatMap((row, y) => row.split('').map((c, x) => (c === ch ? `M${x} ${y}h1v1h-1z` : ''))).join('');
const PX = { hat: layer('H'), skin: layer('S'), eye: layer('E'), coat: layer('C'), accent: layer('A'), legs: layer('L') };

export function Person({ hat, skin = '#F2C9A0', coat = '#ECEAFF', legs = '#3B3766', size = 40, bob = false, delay = 0, opacity = 1 }) {
  return (
    <svg className={bob ? 'bob' : undefined} viewBox="0 0 10 12" width={size} height={size * 1.2} shapeRendering="crispEdges"
      aria-hidden="true" style={{ animationDelay: `${delay}s`, opacity, flexShrink: 0 }}>
      <path d={PX.hat} fill={hat} /><path d={PX.skin} fill={skin} /><path d={PX.eye} fill="#1B1A2E" />
      <path d={PX.coat} fill={coat} /><path d={PX.accent} fill={hat} /><path d={PX.legs} fill={legs} />
    </svg>
  );
}

export function Book() {
  return (
    <svg viewBox="0 0 14 10" width="56" height="40" shapeRendering="crispEdges" aria-hidden="true">
      <rect x="0" y="1" width="6" height="8" fill="#ECEAFF" /><rect x="7" y="1" width="6" height="8" fill="#ECEAFF" />
      <rect x="6" y="0" width="1" height="10" fill="#3B3766" /><rect x="1" y="3" width="4" height="1" fill="#7CF29C" />
      <rect x="1" y="5" width="3" height="1" fill="#7CF29C" /><rect x="8" y="3" width="4" height="1" fill="#7CF29C" />
      <rect x="9" y="5" width="2" height="2" fill="#FF6AD5" />
    </svg>
  );
}

export function Board() {
  return (
    <svg viewBox="0 0 16 10" width="80" height="50" shapeRendering="crispEdges" aria-hidden="true">
      <rect x="0" y="0" width="16" height="10" fill="#6B4A2E" /><rect x="1" y="1" width="14" height="8" fill="#1F4D3A" />
      <rect x="2" y="3" width="3" height="1" fill="#ECEAFF" /><rect x="6" y="3" width="1" height="1" fill="#ECEAFF" />
      <rect x="8" y="3" width="4" height="1" fill="#ECEAFF" /><rect x="2" y="6" width="5" height="1" fill="#ECEAFF" />
      <rect x="9" y="6" width="3" height="1" fill="#FFD447" />
    </svg>
  );
}

export function Window() {
  return (
    <svg viewBox="0 0 12 12" width="60" height="60" shapeRendering="crispEdges" aria-hidden="true">
      <rect x="0" y="0" width="12" height="12" fill="#6B4A2E" /><rect x="1" y="1" width="10" height="10" fill="#05051A" />
      <rect x="5" y="1" width="1" height="10" fill="#6B4A2E" /><rect x="1" y="5" width="10" height="1" fill="#6B4A2E" />
      <rect x="2" y="2" width="1" height="1" fill="#FFD447" /><rect x="8" y="3" width="1" height="1" fill="#F2F0FF" />
      <rect x="3" y="8" width="1" height="1" fill="#F2F0FF" /><rect x="9" y="8" width="1" height="1" fill="#5CE1E6" />
    </svg>
  );
}

export function Sleep({ label }) {
  return (
    <svg className="twinkle" viewBox="0 0 8 8" width="24" height="24" shapeRendering="crispEdges" role="img" aria-label={label} style={{ alignSelf: 'flex-start' }}>
      {[[5, 0, 3], [6, 1, 1], [5, 2, 3], [0, 4, 4], [2, 5, 1], [1, 6, 1], [0, 7, 4]].map(([x, y, w]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={w} height="1" fill="#B8B4E0" />
      ))}
    </svg>
  );
}

export function Envelope() {
  return (
    <svg viewBox="0 0 14 10" width="42" height="30" shapeRendering="crispEdges" aria-hidden="true">
      <rect x="0" y="0" width="14" height="10" fill="#ECEAFF" />
      {[[1, 1], [2, 2], [3, 3], [4, 4], [12, 1], [11, 2], [10, 3], [9, 4]].map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill="#3B3766" />
      ))}
      <rect x="5" y="4" width="4" height="4" fill="#FF6AD5" /><rect x="6" y="5" width="2" height="2" fill="#C2479F" />
    </svg>
  );
}

export function Tomb({ size = 56, label }) {
  return (
    <svg viewBox="0 0 8 10" width={size} height={size * 1.25} shapeRendering="crispEdges" role={label ? 'img' : undefined}
      aria-label={label} aria-hidden={label ? undefined : 'true'}>
      <rect x="1" y="1" width="6" height="9" fill="#8A88B0" /><rect x="2" y="0" width="4" height="1" fill="#8A88B0" />
      <rect x="3" y="3" width="2" height="1" fill="#3B3766" /><rect x="3.5" y="2" width="1" height="3" fill="#3B3766" />
    </svg>
  );
}
