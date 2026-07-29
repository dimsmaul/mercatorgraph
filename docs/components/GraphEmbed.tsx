const WORKER_URL = process.env.NEXT_PUBLIC_WORKER_URL ?? 'http://localhost:8000';

/** Embeds graphify's interactive graph.html for a project (served by the worker). */
export function GraphEmbed({ slug }: { slug: string }) {
  return (
    <iframe
      src={`${WORKER_URL}/projects/${slug}/graph.html`}
      title={`graph: ${slug}`}
      className="w-full rounded-lg border"
      style={{ height: 480 }}
      loading="lazy"
    />
  );
}
