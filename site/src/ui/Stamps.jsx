const ZTF = 1.012; // arcseconds in a ZTF pixel

// cutouts from one image strip at a whole number of screen pixels per ZTF pixel, never smoothed
export default function Stamps({ src, size, tile, gap = 0, pixel = 1, scale = 2, labels, alt, arcsec }) {
  const k = Math.max(1, Math.round(scale)) / pixel;
  return (
    <figure className="stamps" role="img" aria-label={alt}>
      <div className="tiles">
        {labels.map((name, i) => (
          <div key={name} className="tile">
            <i style={{
              width: tile * k, height: tile * k, backgroundImage: `url(${src})`,
              backgroundSize: `${size[0] * k}px ${size[1] * k}px`, backgroundPosition: `${-i * (tile + gap) * k}px 0`,
            }} />
            <span>{name}</span>
          </div>
        ))}
      </div>
      {arcsec && <div className="scalebar"><i style={{ width: Math.round((arcsec / ZTF) * Math.round(scale)) }} />{arcsec}″</div>}
    </figure>
  );
}
