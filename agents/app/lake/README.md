# Content lake + hybrid index (D9)

The single ingest target for **all** raw material, with a hybrid index queried on demand. One Mongo
instance backs both this lake and the work-state store (§7); the lake reuses the work-state Mongo
patterns (`MongoModel` + `BaseRepository`). Domain model: `report.md` §1.4 (item), §3 (store owner).

This ticket builds **the lake + the index + the ingest/query API**. It builds **no connectors** and
**no Oracle** — those are separate downstream tickets that plug into the two seams below.

## The two seams

- **Ingest** — `ContentLake.ingest(item)` / `.ingest_many(items)`. Push / on-refresh entrypoint the
  *connectors* ticket calls. Connector-agnostic: a connector builds a `ContentLakeItem`
  (raw content, origin `source_id`, inherited `classification`, `metadata`) and hands it over. The
  lake indexes it **on ingest** (embedding + keyword tokens), defaults `content_date`, writes it.
  Nothing is ever deleted (`ContentLakeRepository.delete` raises).
- **Query** — `ContentLake.query(LakeQuery) -> list[RankedCandidate]`. On-demand hybrid query the
  *Oracle*, *research sidecar*, and *drafting* call. Semantic + keyword + structured-metadata, with
  a recency window and a hard `top_k` cap (rank-and-retrieve; never returns the whole lake).

Both are also exposed over REST: `POST /api/lake/ingest`, `POST /api/lake/query` (see `routes.py`).

## The hybrid index — three legs

| Leg | Local backend (default) | Atlas backend (production) |
|-----|-------------------------|-----------------------------|
| **Semantic** | `HashingEmbedder` vectors + brute-force cosine in Python | real embedding model + `$vectorSearch` on the `embedding` field |
| **Keyword / full-text** | pre-tokenized `keyword_tokens` + fraction-of-terms overlap | Atlas `$search` (BM25) over `raw_content` |
| **Structured metadata** | native Mongo `$match` (`ContentLakeRepository.build_filter`) | the *same* filter, pushed into the `$vectorSearch`/`$search` stages |

The metadata + recency legs are **hard pre-filters**; semantic + keyword are **soft scores**
blended by the per-query weights. Setting a weight to 0 gives a pure single-mode query; omitting
`text` makes it a recency browse.

## Atlas vs. local — the difference, and why it's a config flip

`mongo:7` (compose) and the in-memory test double have **no Atlas Vector/Search**, so the default
`lake_index_backend="local"` runs a working fallback with an identical query surface
(`LakeQuery` → `RankedCandidate`). Production sets `lake_index_backend="atlas"` (and a real
`embedding_backend` + key). No caller changes: `ContentLake`, `LakeQuery`, and `RankedCandidate`
are identical across backends (`index.py`).

Behavioural differences to know:

- **Ranking math.** Local blends relu-cosine + term-overlap linearly. Atlas fuses `$vectorSearch`
  and `$search` rankings with reciprocal rank fusion (RRF). Ordering is comparable; absolute
  `score` values are not, and `RankedCandidate.semantic_score`/`keyword_score` are cosine/overlap
  locally vs. normalized rank signals on Atlas.
- **Embeddings.** `HashingEmbedder` is lexical (shared vocabulary → higher cosine), not a semantic
  model. A real provider gives true semantic similarity; the vector width must match
  `embedding_dim` and the Atlas vector index.
- **Scale.** Local cosine is brute-force over the pre-filtered candidate set — fine for dev/UAT,
  not for a large production lake. Atlas does ANN vector search + indexed full-text.

### Required Atlas indexes (`content_lake` collection)

Create these once per environment; then flip the config. `AtlasHybridIndex` references them by name
(`content_lake_vector`, `content_lake_search`).

Vector index (`content_lake_vector`) — width must equal `embedding_dim`:

```json
{
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 256, "similarity": "cosine" },
    { "type": "filter", "path": "source_id" },
    { "type": "filter", "path": "classification" },
    { "type": "filter", "path": "metadata.author" },
    { "type": "filter", "path": "metadata.tags" },
    { "type": "filter", "path": "metadata.content_date" }
  ]
}
```

Atlas Search index (`content_lake_search`):

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "raw_content": { "type": "string" },
      "source_id": { "type": "token" },
      "classification": { "type": "token" },
      "metadata": {
        "type": "document",
        "fields": {
          "author": { "type": "token" },
          "tags": { "type": "token" },
          "content_date": { "type": "date" }
        }
      }
    }
  }
}
```

> `AtlasHybridIndex` is exercised only against a real Atlas cluster and is **not** covered by the
> local pytest suite (which covers `LocalHybridIndex`). It is included so production wiring is the
> config flip described here, not a rewrite.
