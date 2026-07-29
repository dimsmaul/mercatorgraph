'use client';

import { useEffect, useState } from 'react';

/** Embeds graphify's interactive graph.html for a project (served by the worker).
 *  Worker URL is resolved at runtime from /api/config, not baked at build. */
export function GraphEmbed({ slug }: { slug: string }) {
  const [base, setBase] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((c) => setBase(c.workerUrl))
      .catch(() => {});
  }, []);

  if (!base) return null;
  return (
    <iframe
      src={`${base}/projects/${slug}/graph.html`}
      title={`graph: ${slug}`}
      className="w-full rounded-lg border"
      style={{ height: 480 }}
      loading="lazy"
    />
  );
}
