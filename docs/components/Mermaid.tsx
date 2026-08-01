'use client';

import { useEffect, useId, useRef, useState } from 'react';

// Client-side mermaid renderer. Diagrams are authored as <Mermaid chart={`...`} /> in MDX.
export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, '');
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      const mermaid = (await import('mermaid')).default;
      mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' });
      try {
        const { svg } = await mermaid.render(`m-${id}`, chart);
        if (active) setSvg(svg);
      } catch (e) {
        if (active) setSvg(`<pre>${String(e)}</pre>`);
      }
    })();
    return () => {
      active = false;
    };
  }, [chart, id]);

  return <div ref={ref} className="my-4 flex justify-center" dangerouslySetInnerHTML={{ __html: svg }} />;
}
