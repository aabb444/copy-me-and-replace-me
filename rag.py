"""
向量检索模块 —— 基于 ChromaDB 的本地知识库 RAG
============================================
为聊天提供知识库上下文增强，提高回答准确度。
"""
import re
import json
import hashlib
from pathlib import Path

CODEX_DIR = Path.home() / ".codex"
VAULT_DIR = CODEX_DIR / "vault"
CHROMA_DIR = CODEX_DIR / "chroma_db"

try:
    import chromadb
    from chromadb.config import Settings
    _HAS_CHROMA = True
except ImportError:
    _HAS_CHROMA = False


def _get_client():
    """获取 ChromaDB 客户端。"""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def _chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """将文本分块。"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
        if start >= len(text):
            break
    return chunks


def _simple_embed(text: str, dim: int = 128) -> list[float]:
    """不需要外部模型的轻量级嵌入 —— 基于字符哈希的固定维度向量。

    虽然不是真正的语义嵌入，但比纯关键词搜索好，
    而且不依赖任何外部下载。
    """
    vec = [0.0] * dim
    for i, ch in enumerate(text):
        h = int(hashlib.md5(f"{i}:{ch}".encode()).hexdigest()[:8], 16)
        idx = h % dim
        vec[idx] += 1.0 + (h % 10) / 10.0

    # 归一化
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def index_vault():
    """扫描 vault/ 下所有笔记，写入 ChromaDB 向量库。"""
    if not _HAS_CHROMA:
        return {"error": "chromadb not installed"}

    try:
        client = _get_client()
        # 删除旧集合重建
        try:
            client.delete_collection("vault")
        except:
            pass
        collection = client.create_collection("vault")

        ids = []
        documents = []
        metadatas = []

        for fp in sorted(VAULT_DIR.rglob("*.md")):
            text = fp.read_text(encoding="utf-8")
            # 去掉 frontmatter
            clean = re.sub(r'^---.*?---\s*', '', text, flags=re.DOTALL).strip()
            if not clean:
                continue

            chunks = _chunk_text(clean)
            for i, chunk in enumerate(chunks):
                doc_id = f"{fp.relative_to(VAULT_DIR)}#{i}"
                ids.append(doc_id)
                documents.append(chunk)
                metadatas.append({
                    "filename": fp.name,
                    "path": str(fp.relative_to(VAULT_DIR)),
                })

        if not ids:
            return {"indexed": 0}

        # 批量添加
        embeddings = [_simple_embed(d) for d in documents]
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return {"indexed": len(ids), "chunks": len(ids)}
    except Exception as e:
        return {"error": str(e)}


def search_vault(query: str, n_results: int = 5) -> list[dict]:
    """在 vault 中搜索最相关的内容片段。"""
    if not _HAS_CHROMA:
        return []

    try:
        client = _get_client()
        collection = client.get_collection("vault")
        query_vec = _simple_embed(query)
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=n_results,
        )

        hits = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                hits.append({
                    "content": results["documents"][0][i][:500],
                    "filename": results["metadatas"][0][i].get("filename", ""),
                    "score": round(1.0 - results["distances"][0][i], 3) if results.get("distances") else 0,
                })
        return hits
    except Exception:
        return []


def build_rag_context(query: str, max_chars: int = 1500) -> str:
    """构建 RAG 上下文字符串，附加到聊天提示中。"""
    hits = search_vault(query, n_results=4)
    if not hits:
        return ""

    parts = ["\n\n[相关知识库参考]:\n"]
    total = 0
    for h in hits:
        snippet = f"- [{h['filename']}] {h['content'][:400]}"
        total += len(snippet)
        if total > max_chars:
            break
        parts.append(snippet)

    return "\n".join(parts)
