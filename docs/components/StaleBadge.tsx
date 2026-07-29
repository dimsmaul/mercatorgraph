'use client';

import { useEffect, useState } from 'react';

const WORKER_URL = process.env.NEXT_PUBLIC_WORKER_URL ?? 'http://localhost:8000';

/**
 * Shows a warning when the project's latest succeeded build is newer than the
 * graph version this page was generated from (pipeline A staleness model).
 */
export function StaleBadge({
  project,
  graphVersion,
}: {
  project?: string;
  graphVersion?: string;
}) {
  const [latest, setLatest] = useState<string | null>(null);

  useEffect(() => {
    if (!project || !graphVersion) return;
    let cancelled = false;
    fetch(`${WORKER_URL}/projects/${project}/status`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data?.version_ts) return;
        if (String(data.version_ts) > graphVersion) setLatest(data.version_ts);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [project, graphVersion]);

  if (!latest) return null;
  return (
    <div className="my-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
      ⚠ Graph rebuilt ({latest}) since this page was generated ({graphVersion}).
      Docs may be stale.
    </div>
  );
}
