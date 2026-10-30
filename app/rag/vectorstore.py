import os
import time
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_embeddings = None
_vectorstore = None
_bm25_retriever: Optional[BM25Retriever] = None
_all_documents_corpus: List[Document] = []

EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "all-minilm-l6-v2": 384,
}


def get_embedding_dimension(model_name: str | None = None) -> int:
    name = (model_name or settings.embedding_model or "").strip().lower()
    if not name:
        return 1536
    if name in EMBEDDING_DIMENSIONS:
        return EMBEDDING_DIMENSIONS[name]
    if "text-embedding-3-small" in name:
        return 1536
    if "text-embedding-3-large" in name:
        return 3072
    if "text-embedding-ada-002" in name:
        return 1536
    if "all-minilm" in name:
        return 384
    return 1536


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        if settings.openai_api_key:
            from langchain_openai import OpenAIEmbeddings
            _embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key,
            )
        else:
            # Fallback for environments without live OpenAI API Key
            logger.info("Using local fast embeddings for dev/fallback mode.")
            from langchain_core.embeddings import Embeddings
            import hashlib
            import numpy as np

            class LocalDeterministicEmbeddings(Embeddings):
                """Fast deterministic embedding fallback for development and isolated environments."""
                def __init__(self, dim: int = 1536):
                    self.dim = dim

                def _embed(self, text: str) -> List[float]:
                    h = hashlib.sha256(text.encode("utf-8")).digest()
                    np.random.seed(int.from_bytes(h[:4], "little"))
                    vec = np.random.randn(self.dim)
                    norm = np.linalg.norm(vec)
                    return (vec / (norm + 1e-9)).tolist()

                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                    return [self._embed(t) for t in texts]

                def embed_query(self, text: str) -> List[float]:
                    return self._embed(text)

            _embeddings = LocalDeterministicEmbeddings(get_embedding_dimension())
    return _embeddings


def ensure_pinecone_index():
    if not settings.pinecone_api_key:
        return None

    try:
        from pinecone import Pinecone, ServerlessSpec
        desired_dimension = get_embedding_dimension()
        pc = Pinecone(api_key=settings.pinecone_api_key)
        existing_indexes = [x["name"] for x in pc.list_indexes()]

        if settings.pinecone_index_name not in existing_indexes:
            logger.info("Creating Pinecone index: %s (dim=%d)", settings.pinecone_index_name, desired_dimension)
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=desired_dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            while not pc.describe_index(settings.pinecone_index_name).status["ready"]:
                time.sleep(1)

        return pc.Index(settings.pinecone_index_name)
    except Exception as exc:
        logger.warning("Could not connect to Pinecone: %s. Using in-memory vector store.", exc)
        return None


def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        index = ensure_pinecone_index()
        if index is not None and settings.pinecone_api_key:
            from langchain_pinecone import PineconeVectorStore
            _vectorstore = PineconeVectorStore(
                index=index,
                embedding=get_embeddings(),
                namespace=settings.pinecone_namespace,
            )
        else:
            # In-memory vector store for resilient development/local execution
            from langchain_core.vectorstores import InMemoryVectorStore
            logger.info("Initializing in-memory dense vector store fallback.")
            _vectorstore = InMemoryVectorStore(embedding=get_embeddings())
            # Pre-seed with default knowledge base documents
            _seed_default_corpus()
    return _vectorstore


def _seed_default_corpus():
    """Seeds the in-memory store and BM25 corpus from data/sample_kb."""
    from app.services.ingestion import load_file, chunk_documents
    sample_dir = Path(settings.sample_kb_dir)
    if sample_dir.exists():
        docs = []
        for file_path in sample_dir.glob("*.*"):
            try:
                docs.extend(load_file(file_path))
            except Exception as e:
                logger.debug("Could not pre-load %s: %s", file_path, e)
        if docs:
            chunks = chunk_documents(docs)
            add_documents(chunks)


def get_bm25_retriever() -> BM25Retriever:
    """Returns or creates the sparse BM25 retriever."""
    global _bm25_retriever, _all_documents_corpus
    if _bm25_retriever is None:
        if not _all_documents_corpus:
            _seed_default_corpus()
        
        if _all_documents_corpus:
            _bm25_retriever = BM25Retriever.from_documents(
                _all_documents_corpus,
                k=settings.top_k
            )
        else:
            # Minimal seed to prevent empty corpus exception
            default_doc = Document(
                page_content="NovaRetail Enterprise IT Support Portal: VPN, Password Reset, MFA Policies.",
                metadata={"source": "system_bootstrap"}
            )
            _bm25_retriever = BM25Retriever.from_documents([default_doc], k=settings.top_k)

    return _bm25_retriever


class HybridRetriever:
    """
    Enterprise Hybrid RAG Retriever:
    Fuses Dense Vector Search (Pinecone/InMemory) + Sparse Keyword Search (BM25)
    using Reciprocal Rank Fusion (RRF).
    """
    def __init__(
        self,
        dense_store=None,
        bm25_retriever=None,
        k: int = 4,
        rrf_k: int = 60,
        dense_weight: float = 0.5,
        bm25_weight: float = 0.5,
    ):
        self.dense_store = dense_store or get_vectorstore()
        self.bm25_retriever = bm25_retriever
        self.k = k
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight

    def invoke(self, query: str) -> List[Document]:
        return self.get_relevant_documents(query)

    def get_relevant_documents(self, query: str) -> List[Document]:
        # 1. Dense retrieval
        try:
            dense_docs = self.dense_store.similarity_search(query, k=self.k * 2)
        except Exception as e:
            logger.warning("Dense retrieval error: %s", e)
            dense_docs = []

        # 2. Sparse BM25 retrieval
        try:
            bm25 = self.bm25_retriever or get_bm25_retriever()
            bm25.k = self.k * 2
            sparse_docs = bm25.invoke(query)
        except Exception as e:
            logger.warning("Sparse BM25 retrieval error: %s", e)
            sparse_docs = []

        # 3. Reciprocal Rank Fusion (RRF)
        # Score(doc) = w_dense / (rrf_k + rank_dense) + w_bm25 / (rrf_k + rank_sparse)
        doc_scores: Dict[str, Tuple[Document, float, int, int]] = {}

        for rank, doc in enumerate(dense_docs):
            key = doc.page_content.strip()[:200]
            score = self.dense_weight / (self.rrf_k + (rank + 1))
            doc_scores[key] = (doc, score, rank + 1, -1)

        for rank, doc in enumerate(sparse_docs):
            key = doc.page_content.strip()[:200]
            score = self.bm25_weight / (self.rrf_k + (rank + 1))
            if key in doc_scores:
                existing_doc, existing_score, d_rank, _ = doc_scores[key]
                doc_scores[key] = (existing_doc, existing_score + score, d_rank, rank + 1)
            else:
                doc_scores[key] = (doc, score, -1, rank + 1)

        # Sort documents by fused RRF score descending
        fused = sorted(doc_scores.values(), key=lambda item: item[1], reverse=True)
        top_fused_docs: List[Document] = []

        for doc, score, d_rank, s_rank in fused[:self.k]:
            meta = dict(doc.metadata)
            meta["rrf_score"] = round(score, 5)
            meta["dense_rank"] = d_rank if d_rank > 0 else "None"
            meta["bm25_rank"] = s_rank if s_rank > 0 else "None"
            meta["retrieval_mode"] = "Hybrid (Dense + BM25 RRF)"
            top_fused_docs.append(Document(page_content=doc.page_content, metadata=meta))

        logger.info(
            "Hybrid RAG retrieved %d dense, %d sparse -> %d fused chunks for query: %s",
            len(dense_docs), len(sparse_docs), len(top_fused_docs), query
        )
        return top_fused_docs


def get_retriever():
    """Returns the configured retriever (Hybrid RAG or Dense)."""
    if settings.enable_hybrid_rag:
        return HybridRetriever(
            dense_store=get_vectorstore(),
            bm25_retriever=get_bm25_retriever(),
            k=settings.top_k,
            rrf_k=settings.rrf_k,
            dense_weight=settings.dense_weight,
            bm25_weight=settings.bm25_weight,
        )
    return get_vectorstore().as_retriever(search_kwargs={"k": settings.top_k})


def add_documents(chunks: List[Document]) -> List[str]:
    """Adds documents to both Dense store and Sparse BM25 corpus simultaneously."""
    global _bm25_retriever, _all_documents_corpus
    
    # Add to BM25 in-memory corpus
    _all_documents_corpus.extend(chunks)
    _bm25_retriever = BM25Retriever.from_documents(_all_documents_corpus, k=settings.top_k)

    # Add to dense vectorstore
    store = get_vectorstore()
    try:
        ids = store.add_documents(chunks)
        return ids or [f"id-{i}" for i in range(len(chunks))]
    except Exception as exc:
        logger.warning("Error adding documents to primary store: %s", exc)
        return [f"id-{i}" for i in range(len(chunks))]
