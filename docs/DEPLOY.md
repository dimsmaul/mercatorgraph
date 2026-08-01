# Deploying the docs site to Vercel

This `docs/` folder is a standalone Fumadocs (Next.js) site — the public documentation for
Mercatorgraph. It is **not** part of the runtime stack and is not a released Docker image.

## Vercel setup (monorepo subfolder)

The repo is a monorepo; the docs site lives in `docs/`. In the Vercel project:

1. **New Project** → import `dimsmaul/mercatorgraph`.
2. **Root Directory** → set to `docs`.
3. Framework preset: **Next.js** (auto-detected).
4. Build command: `bun run build` (or leave default — it runs the `build` script).
5. Install command: default. The `postinstall` script generates the Fumadocs `.source` files.
6. Deploy.

That's it — no environment variables are required for the docs site.

## How the build works

`.source/` (Fumadocs' generated content index) is gitignored, so it must be generated at build
time. Both are wired:

- `"postinstall": "fumadocs-mdx"` — runs after `bun install` / `npm install`.
- `"build": "fumadocs-mdx && next build"` — regenerates before building, belt-and-suspenders.

So a clean checkout builds correctly on Vercel with no manual steps.

## Local preview

```bash
cd docs
bun install
bun run dev      # http://localhost:3000
# or a production build:
bun run build && bun run start
```

## Editing content

Docs pages are MDX under `content/docs/`. Sidebar order is `content/docs/meta.json`.
Diagrams use the `<Mermaid chart={`...`} />` component (see `architecture.mdx`).
