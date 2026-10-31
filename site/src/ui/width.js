import { useLayoutEffect, useRef, useState } from 'react';

// an element's width in CSS pixels, kept current as the page resizes
export function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  return [ref, width];
}
