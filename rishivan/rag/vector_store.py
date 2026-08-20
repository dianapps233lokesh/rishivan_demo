"""Backend-agnostic vector store for the RAG POC.

Embeddings are computed by Vertex (text-embedding-004) and handed to the store
as finished vectors, so the backend only stores and searches them. Two
implementations — ChromaDB (embedded, local folder) and Qdrant (server / Cloud)
— behind one interface, selected by ``settings.VECTOR_BACKEND``.

A "hit" is normalised across backends as ``{"document": str, "metadata": dict}``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from rishivan.config import settings

Hit = dict  # {"document": str, "metadata": dict}


class VectorStore(ABC):
    """Storage/query interface shared by the Chroma and Qdrant backends."""

    @abstractmethod
    def reset(self) -> None:
        """Drop the collection so a fresh embed run starts clean."""

    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Insert/replace points; create the collection on first call if needed."""

    @abstractmethod
    def search(self, embedding: list[float], n_results: int) -> list[Hit]:
        """Nearest-neighbour search; returns normalised hits."""

    @abstractmethod
    def search_filtered(
        self,
        embedding: list[float],
        n_results: int,
        domain_filter: list[str],
    ) -> list[Hit]:
        """Search with metadata filter on ``book_domain``."""

    @abstractmethod
    def search_batch(
        self, embeddings: list[list[float]], n_results: int
    ) -> list[list[Hit]]:
        """Search many query vectors in one round-trip; one hit-list per query."""

    @abstractmethod
    def search_batch_filtered(
        self,
        embeddings: list[list[float]],
        n_results: int,
        domain_filter: list[str],
    ) -> list[list[Hit]]:
        """Batch search with domain filter on ``book_domain``."""

    @abstractmethod
    def fetch_pages(self, pages_by_doc: dict[int, list[int]]) -> list[Hit]:
        """Fetch every element on the given pages per document (page-window)."""

    @abstractmethod
    def count(self) -> int:
        """Number of stored points (0 if the collection is absent)."""

    @abstractmethod
    def exists(self) -> bool:
        """Whether the collection has been created and is queryable."""

    @abstractmethod
    def all_points(self, batch: int = 512) -> list[Hit]:
        """Every point in the collection, ignoring similarity entirely.

        Needed by the rule base, where similarity is the wrong entry point. Measured on
        the real corpus: nominating rules by similarity to the question surfaced 10 of the
        21 rules actually true of a chart, losing the rest -- because similarity cannot
        know what is true, so it spends its window on rules that merely read like the
        question. Exact matching has to see everything.
        """


class ChromaVectorStore(VectorStore):
    """Embedded ChromaDB backed by a local folder."""

    def __init__(self, path: str, collection_name: str):
        import chromadb

        self._client = chromadb.PersistentClient(path=path)
        self._name = collection_name
        self._collection = None

    def _get(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(name=self._name)
        return self._collection

    def reset(self) -> None:
        try:
            self._client.delete_collection(name=self._name)
        except Exception:
            pass
        self._collection = None

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        self._get().upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def search(self, embedding, n_results) -> list[Hit]:
        return self.search_batch([embedding], n_results)[0]

    def search_filtered(self, embedding, n_results, domain_filter) -> list[Hit]:
        return self.search_batch_filtered([embedding], n_results, domain_filter)[0]

    def search_batch(self, embeddings, n_results) -> list[list[Hit]]:
        # Chroma queries multiple embeddings in one call: results are per-query.
        res = self._get().query(query_embeddings=embeddings, n_results=n_results)
        out: list[list[Hit]] = []
        for docs, metas in zip(res["documents"], res["metadatas"]):
            out.append(
                [{"document": d, "metadata": m} for d, m in zip(docs, metas)]
            )
        return out

    def search_batch_filtered(self, embeddings, n_results, domain_filter) -> list[list[Hit]]:
        where = {"book_domain": {"$in": domain_filter}} if domain_filter else None
        res = self._get().query(
            query_embeddings=embeddings, n_results=n_results, where=where
        )
        out: list[list[Hit]] = []
        for docs, metas in zip(res["documents"], res["metadatas"]):
            out.append(
                [{"document": d, "metadata": m} for d, m in zip(docs, metas)]
            )
        return out

    def all_points(self, batch: int = 512) -> list[Hit]:
        got = self._get().get()
        return [
            {"document": doc, "metadata": meta}
            for doc, meta in zip(got.get("documents") or [], got.get("metadatas") or [])
        ]

    def fetch_pages(self, pages_by_doc) -> list[Hit]:
        # Translate to Chroma's filter DSL: OR across docs, each doc AND page-in.
        clauses = [
            {
                "$and": [
                    {"document_id": {"$eq": doc}},
                    {"page_number": {"$in": sorted(pages)}},
                ]
            }
            for doc, pages in pages_by_doc.items()
        ]
        where = clauses[0] if len(clauses) == 1 else {"$or": clauses}
        got = self._get().get(where=where)
        return [
            {"document": doc, "metadata": meta}
            for doc, meta in zip(got["documents"], got["metadatas"])
        ]

    def count(self) -> int:
        try:
            return self._client.get_collection(name=self._name).count()
        except Exception:
            return 0

    def exists(self) -> bool:
        try:
            self._client.get_collection(name=self._name)
            return True
        except Exception:
            return False


class QdrantVectorStore(VectorStore):
    """Qdrant server / Cloud backend (payload carries the document + metadata)."""

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

        ``fn_factory`` is called with no arguments and must read ``self._client``
        itself at call time (not close over a stale reference), since a retry
        may swap it out.

        The client is built once and cached for the app's whole lifetime (see
        streamlit_app.py's ``@st.cache_resource``), so its connection pool can
        go stale after long idle stretches — Qdrant Cloud's edge then answers
        a live query with ``421 Misdirected Request``. Critically, a 421 is a
        complete, valid HTTP response, not a connection-level error, so httpx
        has no reason to evict that connection from its pool — simply retrying
        on the SAME client reuses the SAME stale connection and fails again
        every time (verified empirically). Retrying only helps once the
        client itself — and so its whole connection pool — is rebuilt.
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
        if self._client.collection_exists(self._name):
            self._client.delete_collection(self._name)

    # Payload fields filtered on by fetch_pages and domain-filtered search.
    # Unlike Chroma, Qdrant rejects a filter on any field without an explicit
    # payload index.
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
        res = self._with_retry(lambda: self._client.query_points(
            collection_name=self._name,
            query=embedding,
            limit=n_results,
            with_payload=True,
        ))
        return [self._to_hit(p.payload) for p in res.points]

    def search_filtered(self, embedding, n_results, domain_filter) -> list[Hit]:
        res = self._with_retry(lambda: self._client.query_points(
            collection_name=self._name,
            query=embedding,
            limit=n_results,
            with_payload=True,
            query_filter=self._domain_filter(domain_filter),
        ))
        return [self._to_hit(p.payload) for p in res.points]

    def search_batch(self, embeddings, n_results) -> list[list[Hit]]:
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
        if not self._client.collection_exists(self._name):
            return 0
        return self._client.count(collection_name=self._name, exact=True).count

    def exists(self) -> bool:
        return self._client.collection_exists(self._name)

    def all_points(self, batch: int = 512) -> list[Hit]:
        """Scroll the whole collection. Vectors are not fetched -- only payloads."""
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
                with_vectors=False,
            )
            for point in points:
                payload = dict(point.payload or {})
                hits.append(
                    {
                        "document": payload.pop(self._DOC_KEY, ""),
                        "metadata": payload,
                    }
                )
            if offset is None:
                break
        return hits


def get_vector_store(collection_name: str | None = None) -> VectorStore:
    """Construct the configured backend (``settings.VECTOR_BACKEND``).

    ``collection_name`` overrides the configured collection. The rule base lives in its
    own collection beside the pages -- mixing them would let a page hit and a rule hit
    compete on one similarity score, and they are not comparable: a page is evidence to
    read, a rule is a claim to test.
    """
    name = collection_name or settings.VECTOR_COLLECTION
    if settings.VECTOR_BACKEND == "qdrant":
        return QdrantVectorStore(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            collection_name=name,
        )
    return ChromaVectorStore(
        path=settings.CHROMA_PATH,
        collection_name=name,
    )
