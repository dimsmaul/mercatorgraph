import Link from 'next/link';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { baseOptions } from '@/lib/layout.shared';

const features = [
  {
    title: 'One graph, many agents',
    body: 'Build a single knowledge graph per project and serve it to every AI agent through one MCP server — no more 10 duplicated local graphs.',
  },
  {
    title: 'Scoped, not dumped',
    body: 'Every tool result is size-capped. Agents get focused subgraphs, paths, and blast-radius — never the whole graph flooding their context.',
  },
  {
    title: 'Knowledge that persists',
    body: 'Annotations and comments live in Postgres and survive every rebuild — contributed knowledge is never lost when the graph is regenerated.',
  },
  {
    title: 'Atomic, safe builds',
    body: 'One writer per project. Build to staging, validate, promote by an atomic symlink flip. Agents never see a half-built graph.',
  },
  {
    title: 'Wraps Graphify',
    body: 'Graphify is a dependency, not a fork. Mercatorgraph consumes its output and adds centralization, auth, persistence, and a viewer.',
  },
  {
    title: 'Token auth + audit',
    body: 'Per-user and per-agent tokens, scoped per project, with expiry and revocation. Every query is recorded in an audit log.',
  },
];

export default function Home() {
  return (
    <HomeLayout {...baseOptions()}>
    <main className="flex flex-col">
      {/* hero */}
      <section className="mg-hero relative overflow-hidden border-b border-fd-border">
        <div className="mx-auto max-w-4xl px-6 py-24 text-center">
          <p className="mb-4 text-sm font-medium uppercase tracking-widest text-fd-primary">
            Codebase knowledge graph · MCP-native
          </p>
          <h1 className="text-balance text-4xl font-bold tracking-tight sm:text-6xl">
            Mercatorgraph
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-balance text-lg text-fd-muted-foreground">
            One brain for your codebase, many arms for your agents. Turn any repository into a
            centralized, queryable knowledge graph — served to AI agents via a single MCP
            server, and to developers via a graph viewer.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link
              href="/docs"
              className="rounded-lg bg-fd-primary px-6 py-3 text-sm font-semibold text-fd-primary-foreground transition-opacity hover:opacity-90"
            >
              Get Started
            </Link>
            <a
              href="https://github.com/dimsmaul/mercatorgraph"
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-fd-border px-6 py-3 text-sm font-semibold transition-colors hover:bg-fd-accent"
            >
              GitHub
            </a>
          </div>
        </div>
      </section>

      {/* features */}
      <section className="mx-auto w-full max-w-5xl px-6 py-20">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-fd-border bg-fd-card p-6 transition-colors hover:border-fd-primary/60"
            >
              <h3 className="mb-2 font-semibold text-fd-primary">{f.title}</h3>
              <p className="text-sm text-fd-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* closing CTA */}
      <section className="border-t border-fd-border">
        <div className="mx-auto max-w-3xl px-6 py-16 text-center">
          <h2 className="text-2xl font-bold">Run it in one command</h2>
          <pre className="mx-auto mt-6 w-fit rounded-lg border border-fd-border bg-fd-card px-5 py-3 text-left text-sm">
            <code>docker compose up -d</code>
          </pre>
          <div className="mt-8">
            <Link
              href="/docs/getting-started"
              className="text-sm font-semibold text-fd-primary hover:underline"
            >
              Read the getting-started guide →
            </Link>
          </div>
        </div>
      </section>
    </main>
    </HomeLayout>
  );
}
