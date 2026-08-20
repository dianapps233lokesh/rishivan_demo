"""The Qdrant vector store.

Embeddings are computed by Vertex (text-embedding-004) and handed over as finished
vectors, so this only stores and searches them. A "hit" is ``{"document": str,
"metadata": dict}``.
"""

from __future__ import annotations

import time

from rishivan.config import settings

Hit = dict  # {"document": str, "metadata": dict}






class VectorStore:
    """Qdrant server / Cloud store; the payload carries the document and metadata.

    Embeddings arrive as finished vectors, so this only stores and searches them.
    """

    _DOC_KEY = "document"
    _MAX_RETRIES = 3

    def __init__(
        self, url: str, api_key: str, collection_name: str, timeout: int = 120
    ):
        if not url:
            raise ValueError("QDRANT_URL is not configured")
        self._url = url
        self._api_key = api_key
        self._timeout = timeout
        self._name = collection_name
        self._client = self._new_client()

    def _new_client(self):
        from qdrant_client import QdrantClient

        # Generous timeout: Cloud upserts of a full batch can exceed the short
        # httpx default (5s) and abort an otherwise-healthy run.
        return QdrantClient(url=self._url, api_key=self._api_key or None, timeout=self._timeout)

    def _with_retry(self, fn_factory):
        """Retry a transient Qdrant Cloud/network error on a FRESH client.

        ``fn_factory`` takes no arguments and must read ``self._client`` at call time rather
        than closing over a stale reference, since a retry may swap it out.

        The client is cached for the app's lifetime, so its connection pool goes stale after
        long idle stretches and Qdrant Cloud's edge answers with ``421 Misdirected Request``.
        A 421 is a complete valid response, not a connection error, so httpx keeps that
        connection pooled — retrying on the same client reuses the same stale connection and
        fails again every time. Only rebuilding the client, and so the pool, helps.
        """
        last_exc = None
        for attempt in range(self._MAX_RETRIES):
            try:
                return fn_factory()
            except Exception as exc:  # noqa: BLE001 — retry any transport error
                last_exc = exc
                if attempt < self._MAX_RETRIES - 1:
                    self._client = self._new_client()
                    time.sleep(0.5 * (attempt + 1))  # 0.5s, 1s
        raise last_exc

    def reset(self) -> None:
        """Drop the collection so a fresh embed run starts clean."""
        if self._client.collection_exists(self._name):
            self._client.delete_collection(self._name)

    # Payload fields filtered on by fetch_pages and domain-filtered search.
    # Qdrant rejects a filter on any field without an explicit payload index.
    _INDEXED_FIELDS = ("document_id", "page_number")
    _KEYWORD_INDEXED_FIELDS = ("book_domain", "book_slug")

    def _ensure(self, dim: int) -> None:
        from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

        if self._client.collection_exists(self._name):
            return
        self._client.create_collection(
            collection_name=self._name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        for field in self._INDEXED_FIELDS:
            self._client.create_payload_index(
                collection_name=self._name,
                field_name=field,
                field_schema=PayloadSchemaType.INTEGER,
            )
        for field in self._KEYWORD_INDEXED_FIELDS:
            self._client.create_payload_index(
                collection_name=self._name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        """Insert/replace points; create the collection on first call if needed."""
        from qdrant_client.models import PointStruct

        self._ensure(len(embeddings[0]))
        points = [
            PointStruct(
                id=pid,
                vector=vec,
                payload={**meta, self._DOC_KEY: doc},
            )
            for pid, vec, doc, meta in zip(ids, embeddings, documents, metadatas)
        ]
        # Retry transient network errors (via _with_retry, which rebuilds the
        # client between attempts — see its docstring for why that matters);
        # upsert is idempotent (deterministic ids), so a re-sent batch simply
        # overwrites itself.
        self._with_retry(
            lambda: self._client.upsert(collection_name=self._name, points=points)
        )

    def _to_hit(self, payload: dict) -> Hit:
        payload = dict(payload)
        document = payload.pop(self._DOC_KEY, "")
        return {"document": document, "metadata": payload}

    def _domain_filter(self, domain_filter: list[str]):
        """Build a Qdrant Filter for book_domain ∈ domain_filter."""
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        return Filter(
            must=[FieldCondition(key="book_domain", match=MatchAny(any=domain_filter))]
        )

    def search(self, embedding, n_results) -> list[Hit]:
        """Nearest-neighbour search; returns normalised hits."""
        res = self._with_retry(lambda: self._client.query_points(
            collection_name=self._name,
            query=embedding,
            limit=n_results,
            with_payload=True,
        ))
        return [self._to_hit(p.payload) for p in res.points]

    def search_filtered(self, embedding, n_results, domain_filter) -> list[Hit]:
        """Search with metadata filter on ``book_domain``."""
        res = self._with_retry(lambda: self._client.query_points(
            collection_name=self._name,
            query=embedding,
            limit=n_results,
            with_payload=True,
            query_filter=self._domain_filter(domain_filter),
        ))
        return [self._to_hit(p.payload) for p in res.points]

    def search_batch(self, embeddings, n_results) -> list[list[Hit]]:
        """Search many query vectors in one round-trip; one hit-list per query."""
        from qdrant_client.models import QueryRequest

        requests = [
            QueryRequest(query=emb, limit=n_results, with_payload=True)
            for emb in embeddings
        ]
        results = self._with_retry(lambda: self._client.query_batch_points(
            collection_name=self._name, requests=requests
        ))
        return [[self._to_hit(p.payload) for p in r.points] for r in results]

    def search_batch_filtered(self, embeddings, n_results, domain_filter) -> list[list[Hit]]:
        """Batch search with domain filter on ``book_domain``."""
        from qdrant_client.models import QueryRequest

        flt = self._domain_filter(domain_filter)
        requests = [
            QueryRequest(query=emb, limit=n_results, with_payload=True, filter=flt)
            for emb in embeddings
        ]
        results = self._with_retry(lambda: self._client.query_batch_points(
            collection_name=self._name, requests=requests
        ))
        return [[self._to_hit(p.payload) for p in r.points] for r in results]

    def fetch_pages(self, pages_by_doc) -> list[Hit]:
        """Fetch every element on the given pages per document (page-window)."""
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        # OR across docs (should), each doc = document_id AND page_number-in.
        should = [
            Filter(
                must=[
                    FieldCondition(key="document_id", match=MatchValue(value=doc)),
                    FieldCondition(
                        key="page_number", match=MatchAny(any=sorted(pages))
                    ),
                ]
            )
            for doc, pages in pages_by_doc.items()
        ]
        flt = Filter(should=should)

        hits: list[Hit] = []
        offset = None
        while True:
            cursor = offset
            rows, offset = self._with_retry(lambda: self._client.scroll(
                collection_name=self._name,
                scroll_filter=flt,
                with_payload=True,
                limit=256,
                offset=cursor,
            ))
            hits.extend(self._to_hit(p.payload) for p in rows)
            if offset is None:
                break
        return hits

    def count(self) -> int:
        """Number of stored points (0 if the collection is absent)."""
        if not self._client.collection_exists(self._name):
            return 0
        return self._client.count(collection_name=self._name, exact=True).count

    def exists(self) -> bool:
        """Whether the collection has been created and is queryable."""
        return self._client.collection_exists(self._name)

    def all_points(self, batch: int = 512, with_vectors: bool = False) -> list[Hit]:
        """Every point in the collection, ignoring similarity entirely.

        Needed by the rule base, where similarity is the wrong entry point. Measured on
        the real corpus: nominating rules by similarity to the question surfaced 10 of the
        21 rules actually true of a chart, losing the rest -- because similarity cannot
        know what is true, so it spends its window on rules that merely read like the
        question. Exact matching has to see everything.

        """
        """Scroll the whole collection.

        `with_vectors` costs 768 floats per point and is only needed when the caller
        ranks by topical similarity -- which the rule path does, because Rishi relevance
        alone ties almost every rule at 1.0 and cannot order them.
        """
        if not self.exists():
            return []
        hits: list[Hit] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=self._name,
                limit=batch,
                offset=offset,
                with_payload=True,
                with_vectors=with_vectors,
            )
            for point in points:
                payload = dict(point.payload or {})
                hit: Hit = {
                    "document": payload.pop(self._DOC_KEY, ""),
                    "metadata": payload,
                }
                if with_vectors:
                    hit["vector"] = point.vector
                hits.append(hit)
            if offset is None:
                break
        return hits


def get_vector_store(collection_name: str | None = None) -> VectorStore:
    """Build the store, optionally against a named collection.

    The rule base lives in its own collection beside the pages: mixing them would let a
    page hit and a rule hit compete on one similarity score, and they are not comparable
    -- a page is evidence to read, a rule is a claim to test.
    """
    return VectorStore(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        collection_name=collection_name or settings.VECTOR_COLLECTION,
    )
