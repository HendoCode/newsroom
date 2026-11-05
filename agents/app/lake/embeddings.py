"""Embedding provider seam for the semantic leg of the hybrid index (D9).

Production uses a real embedding model whose vectors feed **Atlas Vector Search**. That model is
not wired here (no key, and it is a downstream concern), so this module ships a **deterministic,
dependency-free local embedder** — ``HashingEmbedder`` — behind an ``Embedder`` protocol. Swapping
in a real provider is a config change (``embedding_backend``), not a rewrite: the store and index
only ever see the protocol.

``HashingEmbedder`` uses signed feature hashing (the "hashing trick"): tokens map into a fixed-width
vector, so documents that share vocabulary land close in cosine space — enough to exercise and
locally serve the *same* semantic query surface Atlas will serve in production, and fully
deterministic (stable across processes and runs; no salted ``hash()``, no RNG) so tests are
reproducible.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

# Word-ish tokens: letters/digits runs, lowercased. Shared by the embedder and the keyword leg so
# semantic and full-text signals tokenize identically.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split into alphanumeric tokens. The one tokenizer both index legs share."""
    return _TOKEN_RE.findall(text.lower())


@runtime_checkable
class Embedder(Protocol):
    """A text → vector embedder. The only surface the lake depends on."""

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _hash_ints(token: str) -> tuple[int, int]:
    """Two stable hashes for a token: a bucket index seed and a sign bit.

    Uses blake2b (not the salted builtin ``hash``) so vectors are identical across processes.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value >> 1, value & 1


class HashingEmbedder:
    """Deterministic local embedder via signed feature hashing; L2-normalized output.

    Not a semantic model — it captures lexical overlap in a bounded vector — but it gives a real,
    monotonic cosine signal (more shared vocabulary → higher similarity) and needs no network or
    API key, so the lake's semantic mode works out of the box locally and in tests.
    """

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("embedding dim must be positive")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in tokenize(text):
            bucket_seed, sign_bit = _hash_ints(token)
            idx = bucket_seed % self._dim
            vec[idx] += 1.0 if sign_bit else -1.0
        norm = math.sqrt(sum(component * component for component in vec))
        if norm == 0.0:  # empty / no-token text → zero vector (cosine with it is 0)
            return vec
        return [component / norm for component in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 if either is a zero vector.

    Inputs from ``HashingEmbedder`` are already L2-normalized, so this reduces to a dot product,
    but we normalize defensively so a real provider's un-normalized vectors work unchanged.
    """
    if len(a) != len(b):
        raise ValueError("cosine requires equal-length vectors")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def get_embedder(backend: str = "hashing", *, dim: int = 256) -> Embedder:
    """Construct the configured embedder.

    ``hashing`` (default) → the local, dependency-free embedder. A real provider (e.g. an OpenAI
    or Voyage embedding model feeding Atlas Vector Search) slots in here behind the same protocol
    when ``embedding_backend`` is set and its key is configured server-side.
    """
    normalized = backend.lower()
    if normalized in ("hashing", "local"):
        return HashingEmbedder(dim=dim)
    raise ValueError(
        f"unknown embedding backend {backend!r}; wire the real provider here (D9). "
        "Only the dependency-free 'hashing' backend ships in this ticket."
    )
