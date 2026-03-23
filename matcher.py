"""
matcher.py — 描述相似度匹配模块

两种运行模式（自动选择）：
  1. BGE 模式：onnxruntime + BGE-small-en-v1.5 ONNX 模型，语义质量高
  2. TF-IDF 模式：纯 Python + numpy，无任何 DLL 依赖，兜底保证可用

外部只需调用：
    from matcher import find_best_matches
    results = find_best_matches(customer_desc, db_rows, top_k=5)
"""

import logging
import math
import os
import re
import sys
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 尝试加载 BGE ONNX 模型（失败则静默降级到 TF-IDF）
# ─────────────────────────────────────────────────────────────────────────────

_ort_session   = None   # onnxruntime.InferenceSession
_tokenizer     = None   # transformers tokenizer（仅 BGE 模式需要）
_USE_BGE       = False


def _try_load_bge():
    """尝试加载 BGE-small-en-v1.5 ONNX 模型，失败则返回 False。"""
    global _ort_session, _tokenizer, _USE_BGE
    try:
        import onnxruntime as ort

        # 搜索可能的模型路径
        candidates = [
            # 用户手动放置的路径
            os.path.join(os.path.dirname(__file__), "models", "bge-small-en-v1.5", "model.onnx"),
            os.path.join(os.path.dirname(__file__), "models", "bge-small-en-v1.5.onnx"),
            # HuggingFace 缓存（自动下载后的路径）
            os.path.expanduser(r"~\.cache\huggingface\hub\models--BAAI--bge-small-en-v1.5\snapshots"),
        ]

        onnx_path = None
        for c in candidates:
            if os.path.isfile(c):
                onnx_path = c
                break
            if os.path.isdir(c):
                # snapshots 目录下找 model.onnx
                for root, _, files in os.walk(c):
                    for f in files:
                        if f == "model.onnx":
                            onnx_path = os.path.join(root, f)
                            break
                    if onnx_path:
                        break

        if not onnx_path:
            logger.info("[Matcher] 未找到 BGE ONNX 模型文件，使用 TF-IDF 模式")
            return False

        # 加载 tokenizer（transformers，不依赖 torch）
        from transformers import AutoTokenizer
        tok_dir = os.path.dirname(onnx_path)
        _tokenizer = AutoTokenizer.from_pretrained(tok_dir)

        so = ort.SessionOptions()
        so.log_severity_level = 3
        _ort_session = ort.InferenceSession(onnx_path, sess_options=so,
                                             providers=["CPUExecutionProvider"])
        _USE_BGE = True
        logger.info(f"[Matcher] BGE 模式已启动，模型路径: {onnx_path}")
        return True

    except Exception as e:
        logger.info(f"[Matcher] BGE 加载失败（{e}），降级到 TF-IDF 模式")
        return False


_try_load_bge()  # 模块加载时尝试一次


# ─────────────────────────────────────────────────────────────────────────────
# BGE 编码
# ─────────────────────────────────────────────────────────────────────────────

def _bge_encode(texts: List[str]) -> List[List[float]]:
    """用 BGE ONNX 模型批量编码文本，返回 L2 归一化向量列表。"""
    import numpy as np

    # BGE 建议查询加前缀
    inputs = _tokenizer(
        texts, padding=True, truncation=True,
        max_length=128, return_tensors="np"
    )
    outputs = _ort_session.run(
        None,
        {k: v for k, v in inputs.items() if k in [i.name for i in _ort_session.get_inputs()]}
    )
    # outputs[0] shape: (batch, seq_len, hidden) —— 取 [CLS] token
    embeddings = outputs[0][:, 0, :]   # (batch, hidden)
    # L2 归一化
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return (embeddings / norms).tolist()


# ─────────────────────────────────────────────────────────────────────────────
# TF-IDF 兜底实现（纯 Python，无 DLL 依赖）
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """简单分词：小写 + 按非字母数字分割，过滤短词。"""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return [t for t in tokens if len(t) > 1]


def _tfidf_vectors(corpus: List[str]) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    """
    计算语料库的 TF-IDF 向量。
    返回 (tf_idf_list, idf_dict)
    """
    n = len(corpus)
    tokenized = [_tokenize(doc) for doc in corpus]

    # IDF
    df: Dict[str, int] = {}
    for tokens in tokenized:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((n + 1) / (cnt + 1)) + 1 for t, cnt in df.items()}

    # TF-IDF + L2 归一化
    vectors = []
    for tokens in tokenized:
        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = len(tokens) or 1
        vec: Dict[str, float] = {}
        for t, cnt in tf.items():
            vec[t] = (cnt / total) * idf.get(t, 1.0)
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vec = {t: v / norm for t, v in vec.items()}
        vectors.append(vec)

    return vectors, idf


def _cosine_sparse(a: Dict[str, float], b: Dict[str, float]) -> float:
    """计算两个稀疏向量的余弦相似度（已归一化则直接点积）。"""
    return sum(a.get(t, 0.0) * v for t, v in b.items())


def _tfidf_encode_query(query: str, idf: Dict[str, float]) -> Dict[str, float]:
    """把查询文本编码为 TF-IDF 向量（使用语料库的 IDF）。"""
    tokens = _tokenize(query)
    if not tokens:
        return {}
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = len(tokens)
    vec: Dict[str, float] = {}
    for t, cnt in tf.items():
        vec[t] = (cnt / total) * idf.get(t, 1.0)
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {t: v / norm for t, v in vec.items()}


# ─────────────────────────────────────────────────────────────────────────────
# 主缓存：避免每次查询都重新编码整个价目表
# ─────────────────────────────────────────────────────────────────────────────

_cache: Dict = {
    "mode":     None,   # "bge" | "tfidf"
    "db_texts": [],     # 编码时用的文本列表
    "vectors":  [],     # BGE 模式：List[List[float]]  / TF-IDF 模式：List[Dict]
    "idf":      {},     # 仅 TF-IDF 模式
    "row_indices": [],  # 对应 db_rows 的索引（过滤掉空文本后保留的）
}


def _build_db_text(row: dict) -> str:
    """把一条 FL_DISPLAY 行的描述相关字段拼接为匹配文本。"""
    parts = []
    for key in ["描述", "详情", "报价", "备注1", "备注2"]:
        v = row.get(key, "") or ""
        if v.strip():
            parts.append(v.strip())
    return " | ".join(parts)


def _ensure_cache(db_rows: List[dict]) -> bool:
    """
    确保缓存与当前 db_rows 一致。
    如果行数变了或模式变了，重新构建缓存。
    返回 True 表示缓存可用。
    """
    mode = "bge" if _USE_BGE else "tfidf"
    if (_cache["mode"] == mode and
            len(_cache["db_texts"]) == len(db_rows)):
        return True  # 缓存命中

    logger.info(f"[Matcher] 构建 {mode.upper()} 缓存，共 {len(db_rows)} 行…")

    texts = []
    indices = []
    for i, row in enumerate(db_rows):
        t = _build_db_text(row)
        if t.strip():
            texts.append(t)
            indices.append(i)

    if not texts:
        logger.warning("[Matcher] 价目表无可用描述文本")
        return False

    if mode == "bge":
        try:
            vectors = _bge_encode(texts)
        except Exception as e:
            logger.error(f"[Matcher] BGE 编码失败: {e}")
            return False
        _cache.update({"mode": mode, "db_texts": texts,
                        "vectors": vectors, "idf": {}, "row_indices": indices})
    else:
        vectors, idf = _tfidf_vectors(texts)
        _cache.update({"mode": mode, "db_texts": texts,
                        "vectors": vectors, "idf": idf, "row_indices": indices})

    logger.info(f"[Matcher] 缓存构建完成，有效行数: {len(texts)}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────────────────

def find_best_matches(
    customer_desc: str,
    db_rows: List[dict],
    top_k: int = 5,
    min_score: float = 0.05,
) -> List[Tuple[int, float, dict]]:
    """
    从 db_rows（价目表行，每行是 FL_DISPLAY 字段的 dict）中
    找出与 customer_desc 最相似的 top_k 行。

    返回：[(原始行索引, 相似度分数, row_dict), ...]，按分数降序。
    """
    if not customer_desc or not customer_desc.strip():
        return []
    if not db_rows:
        return []

    if not _ensure_cache(db_rows):
        return []

    mode = _cache["mode"]

    if mode == "bge":
        try:
            import numpy as np
            q_vec = _bge_encode([customer_desc])[0]
            db_mat = _cache["vectors"]
            scores = [
                sum(a * b for a, b in zip(q_vec, db_v))
                for db_v in db_mat
            ]
        except Exception as e:
            logger.error(f"[Matcher] BGE 查询失败: {e}")
            return []
    else:
        q_vec = _tfidf_encode_query(customer_desc, _cache["idf"])
        if not q_vec:
            return []
        scores = [_cosine_sparse(q_vec, db_v) for db_v in _cache["vectors"]]

    # 取 top_k（过滤低分）
    scored = sorted(
        enumerate(scores), key=lambda x: -x[1]
    )[:top_k * 2]  # 多取一些再过滤

    results = []
    for cache_idx, score in scored:
        if score < min_score:
            continue
        row_idx = _cache["row_indices"][cache_idx]
        results.append((row_idx, round(float(score), 4), db_rows[row_idx]))
        if len(results) >= top_k:
            break

    return results


def clear_cache():
    """强制清除缓存（价目表数据更新后调用）。"""
    _cache["mode"] = None
    _cache["db_texts"] = []
    _cache["vectors"] = []
    _cache["idf"] = {}
    _cache["row_indices"] = []
    logger.info("[Matcher] 缓存已清除")


def get_mode() -> str:
    """返回当前使用的匹配模式：'bge' 或 'tfidf'。"""
    return "bge" if _USE_BGE else "tfidf"