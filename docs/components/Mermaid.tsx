'use client';

import { useEffect, useId, useState } from 'react';

// Read a fumadocs CSS custom property from the document root.
function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// Client-side mermaid renderer that follows the fumadocs theme (light/dark) by pulling
// colors from the fd-* CSS variables and re-rendering when the theme toggles.
export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, '');
  const [svg, setSvg] = useState('');
  const [dark, setDark] = useState(false);

  // track theme changes on <html class="dark">
  useEffect(() => {
    const el = document.documentElement;
    const update = () => setDark(el.classList.contains('dark'));
    update();
    const obs = new MutationObserver(update);
    obs.observe(el, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      const mermaid = (await import('mermaid')).default;
      const fg = cssVar('--color-fd-foreground', dark ? '#e6edf3' : '#1f2328');
      const muted = cssVar('--color-fd-muted-foreground', dark ? '#8b949e' : '#59636e');
      const card = cssVar('--color-fd-card', dark ? '#161b22' : '#ffffff');
      const border = cssVar('--color-fd-border', dark ? '#30363d' : '#d0d7de');
      const primary = cssVar('--color-fd-primary', dark ? '#3284f5' : '#096cdc');

      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        fontFamily: 'inherit',
        themeVariables: {
          background: 'transparent',
          primaryColor: card,
          primaryTextColor: fg,
          primaryBorderColor: border,
          secondaryColor: card,
          tertiaryColor: card,
          mainBkg: card,
          nodeBorder: border,
          nodeTextColor: fg,
          textColor: fg,
          lineColor: muted,
          edgeLabelBackground: card,
          clusterBkg: 'transparent',
          clusterBorder: border,
          // sequence diagrams
          actorBkg: card,
          actorBorder: primary,
          actorTextColor: fg,
          signalColor: muted,
          signalTextColor: fg,
          labelBoxBkgColor: card,
          labelBoxBorderColor: border,
          labelTextColor: fg,
          loopTextColor: fg,
          noteBkgColor: card,
          noteTextColor: fg,
          noteBorderColor: border,
        },
      });

      try {
        const { svg } = await mermaid.render(`m-${id}-${dark ? 'd' : 'l'}`, chart);
        if (active) setSvg(svg);
      } catch (e) {
        if (active) setSvg(`<pre>${String(e)}</pre>`);
      }
    })();
    return () => {
      active = false;
    };
  }, [chart, id, dark]);

  return (
    <div
      className="my-4 flex justify-center [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
