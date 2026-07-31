# PRD — Mercatorgraph (Graphify-based)

**Status:** Draft v1
**Tanggal:** 28 Juli 2026
**Owner:** Dimas

---

## 1. Ringkasan

Platform self-hosted yang menjadikan **Graphify** sebagai engine untuk membangun knowledge graph dari codebase, lalu mengekspos hasilnya sebagai **satu sumber kebenaran terpusat** yang bisa dikonsumsi oleh banyak AI agent (via MCP) dan banyak developer (via docs app).

**Prinsip arsitektural utama:** Graphify diperlakukan sebagai **dependency**, bukan fork. Sistem membungkus dan mengonsumsi outputnya (`graphify-out/`), tidak memodifikasi internalnya.

---

## 2. Masalah

Graphify saat ini bersifat lokal dan per-developer:

- 10 developer = 10 graph terduplikasi dan tidak sinkron
- Graph mati bersama sesi; tidak ada persistensi lintas tim
- Agent CI/CD atau agent milik developer lain tidak bisa memanfaatkan graph yang sudah dibangun
- Output Markdown hanya bisa dibaca sebagai file mentah atau `graph.html`; tidak ada navigasi, filter, atau diskusi
- Tidak ada tempat untuk knowledge yang **ditambahkan manusia/agent** (anotasi, konteks "kenapa", keputusan arsitektural) — semuanya hilang saat rebuild

## 3. Tujuan

| # | Tujuan | Ukuran keberhasilan |
|---|--------|---------------------|
| G1 | Satu graph terpusat per project | Semua agent & developer membaca artefak yang sama, tidak ada build lokal duplikat |
| G2 | Akses cepat untuk agent | p95 latensi query MCP < 300 ms |
| G3 | Knowledge yang persisten | Anotasi & komentar bertahan melewati rebuild graph |
| G4 | Multi-project & multi-user | Scoping + auth per project sejak hari pertama |
| G5 | Docs yang bisa dibaca manusia | Developer bisa browse, filter, dan berdiskusi tanpa membuka file mentah |

### Non-Goals (v1)

- Bukan pengganti Graphify; tidak memodifikasi parser/extractor-nya
- Bukan produk SaaS publik — target awal adalah self-hosted internal
- Tidak melakukan ekstraksi kode sendiri
- Tidak ada agent yang menulis langsung ke `graph.json`

---

## 4. Pengguna & Kebutuhan

**Persona A — AI Agent** (Claude Code, Cursor, Codex, agent CI)
Butuh: query terarah dan cepat, jawaban scoped (bukan dump seluruh graph), konteks lintas project.

**Persona B — Developer**
Butuh: memahami codebase asing dengan cepat, menemukan "kenapa" di balik keputusan, meninggalkan catatan yang tidak hilang.

**Persona C — Maintainer platform**
Butuh: rebuild otomatis, visibilitas status build, kontrol akses.

---

## 5. Arsitektur

```
┌─ Docker Compose ─────────────────────────────────────┐
│                                                      │
│  [Worker / Builder]  (Python)                        │
│   • graphify CLI terpasang di image                  │
│   • clone/pull repo → jalankan graphify              │
│   • trigger: webhook push (utama), cron, manual      │
│   • build ke staging → validate → promote (atomik)   │
│                                                      │
│  [Storage]                                           │
│   • graph.json + Markdown, versioned per project     │
│   • Postgres: komentar, anotasi, metadata, user      │
│                                                      │
│  [MCP Server]  (Python + FastMCP)   ← HOT PATH       │
│   • graph di-load ke memori (NetworkX / SQLite FTS)  │
│   • tools scoped, auth via token                     │
│                                                      │
│  [Docs App]  (Fumadocs / Next.js)   ← human only     │
│   • render MD, grouping per project & cluster        │
│   • komentar inline, diff view, embed subgraph       │
└──────────────────────────────────────────────────────┘

Agent     ──► MCP Server ──► Graph Store    (hot path, harus cepat)
Developer ──► Docs App   ──► MD + Postgres  (UX yang diprioritaskan)
```

**Aturan keras:** Agent **tidak pernah** melewati Docs App. MCP server adalah satu-satunya antarmuka agent.

### Pemisahan derived vs contributed knowledge

| Jenis | Sumber | Sifat | Storage |
|-------|--------|-------|---------|
| **Derived** | Hasil ekstraksi Graphify | Rebuildable, boleh ditimpa | `graph.json` + MD (versioned) |
| **Contributed** | Anotasi agent, komentar developer | Harus persisten | Postgres, di-overlay saat query |

Ini pemisahan paling penting di seluruh sistem. Melanggarnya berarti kehilangan knowledge setiap rebuild.

---

## 6. Kontrak Tool MCP

Kontrak ini adalah interface paling mahal untuk diubah. Finalkan sebelum coding.

| Tool | Input | Output | Catatan |
|------|-------|--------|---------|
| `list_projects` | — | daftar project + last_build, node_count | Discovery |
| `query_graph` | `project`, `question`, `max_nodes?` | subgraph + ringkasan | Query utama; harus scoped |
| `get_node` | `project`, `node_id` | detail node + edges langsung + anotasi | |
| `trace_path` | `project`, `from`, `to` | jalur antar node + penjelasan tiap edge | |
| `blast_radius` | `project`, `node_id`, `depth?` | node terdampak jika node ini berubah | Manfaatkan betweenness centrality |
| `search` | `project?`, `query` | hasil FTS lintas node & MD | `project` opsional = cross-project |
| `add_annotation` | `project`, `node_id`, `content` | id anotasi | **Fase 3**, bukan MVP |

**Aturan desain:** setiap tool wajib mengembalikan hasil yang sudah dibatasi ukurannya. Tidak ada endpoint yang mengembalikan `graph.json` utuh — itu menghancurkan context window agent dan menghilangkan keunggulan Graphify (scoped query > baca full report).

Setiap edge tetap membawa tag `EXTRACTED` / `INFERRED` dari Graphify, plus tag ketiga: `CONTRIBUTED` untuk knowledge tambahan.

---

## 7. Performa & Concurrency

**Read:** Graph dimuat ke memori atau SQLite ter-index — **jangan** parse `graph.json` dari disk per query. Banyak agent membaca bersamaan itu murah karena read-only.

**Write — dua jenis berbeda:**

1. *Rebuild graph* — berat tapi jarang. Satu writer per project (lock). Build ke staging, validasi, lalu promote atomik. Agent tidak boleh melihat graph setengah jadi.
2. *Anotasi/komentar* — ringan tapi sering & concurrent. Lewat Postgres, tidak menyentuh `graph.json`.

**Rebuild strategy:** webhook `push` sebagai trigger utama (bukan on-demand) untuk menghindari latensi dan resource contention. Manfaatkan incremental update Graphify (`--update`) agar hanya subgraph yang berubah di-extract ulang.

---

## 8. Auth & Multi-tenancy

- Token per user dan per agent
- Scoping akses per project
- Audit log: siapa query apa, kapan
- Kredensial repo (deploy key / GitHub App) disimpan terenkripsi di sisi worker

---

## 9. Roadmap Bertahap

### Fase 1 — MVP: Centralized Read-Only (Python saja)

Deliverable: worker + MCP server + storage dalam satu `docker-compose`.

- [ ] Dockerfile dengan `uv tool install graphifyy`
- [ ] Worker: clone repo, jalankan graphify, simpan output ter-versioning
- [ ] Trigger webhook push + endpoint manual rebuild
- [ ] Graph loader ke memori / SQLite + FTS
- [ ] MCP server dengan tool: `list_projects`, `query_graph`, `get_node`, `trace_path`, `blast_radius`, `search`
- [ ] Auth token + scoping project
- [ ] Build atomik (staging → promote)

**Belum ada Fumadocs sama sekali di fase ini.** Developer yang penasaran cukup membuka `graph.html` bawaan Graphify.

**Exit criteria:** minimal 2 project ter-index, minimal 3 agent berbeda berhasil query, p95 < 300 ms.

### Fase 2 — Docs App untuk Manusia (Fumadocs)

- [ ] Ingestion MD → content tree Fumadocs dengan frontmatter (project, cluster, tags, confidence)
- [ ] Grouping per project (docs roots/tabs) + filter per Leiden cluster
- [ ] Cross-project search
- [ ] Permalink stabil per node
- [ ] Staleness indicator (halaman yang node-nya berubah sejak build terakhir)
- [ ] Embed subgraph interaktif via komponen MDX

**Kenapa setelah Fase 1:** Docs app adalah konsumen. Membangunnya duluan berarti refactor dua tempat setiap skema berubah.

### Fase 3 — Contributed Knowledge & Feedback Loop

- [ ] Komentar inline block-level (anchor ke heading/block ID) → Postgres
- [ ] Status thread: `open` / `addressed-by-agent` / `resolved`
- [ ] Tool MCP `add_annotation`; anotasi ikut muncul di hasil query
- [ ] Komentar → webhook → job agent → revisi → **buka PR** (bukan tulis langsung)
- [ ] Diff view before/after revisi agent, dengan approval developer

**Prinsip:** agent tidak pernah menulis tanpa review manusia. MD adalah sumber pemahaman codebase.

### Fase 4 — Nice to Have

- Query perubahan graph antar dua release/commit
- Notifikasi staleness ke channel tim
- Dashboard build & usage

---

## 10. Keputusan Teknologi

| Komponen | Pilihan | Alasan |
|----------|---------|--------|
| Worker | Python | Dekat dengan Graphify (Python-native) |
| MCP Server | Python + FastMCP | Satu bahasa dengan graph lib; NetworkX |
| Graph store | NetworkX in-memory / SQLite + FTS | Query milidetik; Postgres jika multi-project berat |
| Metadata store | Postgres | Concurrent write untuk komentar & anotasi |
| Docs app | Fumadocs / Next.js | Komentar inline, diff view, embed graph = React-heavy |
| Deploy | Docker Compose | Self-hosted, polyglot per service |

Polyglot di sini disengaja: docs app adalah keputusan **low-stakes** karena tidak memengaruhi performa agent sama sekali. Bisa diganti belakangan tanpa membongkar apa pun.

---

## 11. Risiko

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Graphify rilis cepat (sudah v8) | Breaking change pada format output | Pin versi di Dockerfile; adapter layer untuk baca `graphify-out/` |
| Ekstraksi docs/PDF butuh LLM | Biaya API terpusat | Batasi mode deep; budget per project; kode tetap gratis via tree-sitter |
| Kode semua project harus bisa diakses server | Risiko keamanan | Deploy key read-only, enkripsi at-rest, self-hosted |
| Graphify (YC-backed) merilis versi hosted sendiri | Overlap fitur | Posisikan sebagai self-hosted internal tool — data tidak keluar server sendiri |
| Feedback loop komentar→agent belum terbukti dipakai | Effort terbuang | Sengaja ditaruh di Fase 3, setelah value inti tervalidasi |

---

## 12. Pertanyaan Terbuka

1. Rebuild per commit atau debounce per N menit untuk repo dengan push frequency tinggi?
2. Cross-project search: apakah semua user boleh melihat semua project, atau ikut scoping token?
3. Apakah anotasi agent perlu approval manusia sebelum muncul di hasil query agent lain?
4. Retensi snapshot graph — simpan berapa versi ke belakang?