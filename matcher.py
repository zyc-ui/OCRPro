"""
matcher.py — 两阶段描述相似度匹配模块

阶段 1 · 类目路由（category_router）
    classify_query(desc) → 识别大类（LIGHTING / CABLE_CONNECTOR / …）
    filter_by_category()  → 从全量价目表中筛出同类候选行
    效果：将搜索空间从 3000+ 行缩减到 30~200 行，消灭跨类目误匹配

阶段 2 · 字段加权精搜（TF-IDF 或 BGE ONNX）
    Stage A — 详情优先：仅对"详情"列打分；
              若最高分 ≥ _DETAILS_PRIORITY_THRESHOLD，视为"详情完全匹配"，
              直接返回结果（优先选择该行）。
    Stage B — 加权组合：详情列未能高分命中时，改用加权文本
              （详情 ×3 + 报价 ×1 + 其余字段 ×1）再次检索，
              确保报价列也被覆盖，且详情列权重始终高于报价列。

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
# 字段加权常量
# ─────────────────────────────────────────────────────────────────────────────

# 详情列精确匹配阈值：TF-IDF / BGE 余弦相似度 ≥ 此值时，视为"详情完全匹配"，
# 直接返回结果，不再继续搜索报价列。可根据实际效果在 0.30~0.55 之间调整。
_DETAILS_PRIORITY_THRESHOLD: float = 0.40

# 加权组合中各字段重复次数（通过 TF 重复拉高权重）
_WEIGHT_DETAILS = 3   # 详情 ×3
_WEIGHT_OFFER   = 1   # 报价 ×1
_WEIGHT_OTHER   = 1   # 描述 / 备注 ×1

# ─────────────────────────────────────────────────────────────────────────────
# 尝试加载 BGE ONNX 模型（失败则静默降级到 TF-IDF）
# ─────────────────────────────────────────────────────────────────────────────

_ort_session = None
_tokenizer   = None
_USE_BGE     = False


def _try_load_bge():
    global _ort_session, _tokenizer, _USE_BGE
    try:
        import onnxruntime as ort

        candidates = [
            os.path.join(os.path.dirname(__file__), "models", "bge-small-en-v1.5", "model.onnx"),
            os.path.join(os.path.dirname(__file__), "models", "bge-small-en-v1.5.onnx"),
            os.path.expanduser(r"~\.cache\huggingface\hub\models--BAAI--bge-small-en-v1.5\snapshots"),
        ]

        onnx_path = None
        for c in candidates:
            if os.path.isfile(c):
                onnx_path = c
                break
            if os.path.isdir(c):
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

        from transformers import AutoTokenizer
        tok_dir    = os.path.dirname(onnx_path)
        _tokenizer = AutoTokenizer.from_pretrained(tok_dir)

        so = ort.SessionOptions()
        so.log_severity_level = 3
        _ort_session = ort.InferenceSession(
            onnx_path, sess_options=so, providers=["CPUExecutionProvider"]
        )
        _USE_BGE = True
        logger.info(f"[Matcher] BGE 模式已启动，模型路径: {onnx_path}")
        return True

    except Exception as e:
        logger.info(f"[Matcher] BGE 加载失败（{e}），降级到 TF-IDF 模式")
        return False


_try_load_bge()


# ─────────────────────────────────────────────────────────────────────────────
# BGE 编码
# ─────────────────────────────────────────────────────────────────────────────

def _bge_encode(texts: List[str]) -> List[List[float]]:
    import numpy as np
    inputs  = _tokenizer(texts, padding=True, truncation=True, max_length=128, return_tensors="np")
    outputs = _ort_session.run(
        None,
        {k: v for k, v in inputs.items() if k in [i.name for i in _ort_session.get_inputs()]}
    )
    embeddings = outputs[0][:, 0, :]
    norms      = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms      = np.where(norms == 0, 1, norms)
    return (embeddings / norms).tolist()


# ─────────────────────────────────────────────────────────────────────────────
# TF-IDF 兜底实现
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """
    技术描述增强分词：
    - 保留数字+单位组合（12w, 85-265vac, 5.5-4）作为独立 token
    - 普通字母词按常规切分
    """
    text = text.lower()
    num_unit = re.findall(r"\d+[\.\-]?\d*\s*[a-z]{1,5}", text)
    words    = re.findall(r"[a-z][a-z0-9]+", text)
    return [t.replace(" ", "") for t in num_unit] + [w for w in words if len(w) > 1]


def _tfidf_vectors(corpus: List[str]) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    n        = len(corpus)
    tokenized = [_tokenize(doc) for doc in corpus]

    df: Dict[str, int] = {}
    for tokens in tokenized:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log((n + 1) / (cnt + 1)) + 1 for t, cnt in df.items()}

    vectors = []
    for tokens in tokenized:
        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = len(tokens) or 1
        vec: Dict[str, float] = {t: (cnt / total) * idf.get(t, 1.0) for t, cnt in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vec  = {t: v / norm for t, v in vec.items()}
        vectors.append(vec)

    return vectors, idf


def _cosine_sparse(a: Dict[str, float], b: Dict[str, float]) -> float:
    return sum(a.get(t, 0.0) * v for t, v in b.items())


def _tfidf_encode_query(query: str, idf: Dict[str, float]) -> Dict[str, float]:
    tokens = _tokenize(query)
    if not tokens:
        return {}
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = len(tokens)
    vec   = {t: (cnt / total) * idf.get(t, 1.0) for t, cnt in tf.items()}
    norm  = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {t: v / norm for t, v in vec.items()}


# ─────────────────────────────────────────────────────────────────────────────
# 文本构建辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _build_details_text(row: dict) -> str:
    """
    仅提取"详情"列文本，用于 Stage A 精确匹配。
    返回空字符串表示该行详情列为空。
    """
    return (row.get("详情") or "").strip()


def _build_weighted_text(row: dict) -> str:
    """
    构建加权组合文本（Stage B 兜底）：
      - 详情 ×_WEIGHT_DETAILS（重复拉高 TF，权重最高）
      - 报价 ×_WEIGHT_OFFER
      - 描述 / 备注1 / 备注2 ×_WEIGHT_OTHER

    若所有字段均为空，退化到原始拼接方式。
    """
    det = (row.get("详情") or "").strip()
    off = (row.get("报价") or "").strip()

    parts: List[str] = []
    if det:
        parts.extend([det] * _WEIGHT_DETAILS)
    if off:
        parts.extend([off] * _WEIGHT_OFFER)

    for key in ["描述", "备注1", "备注2"]:
        v = (row.get(key) or "").strip()
        if v:
            parts.extend([v] * _WEIGHT_OTHER)

    # 全部为空时的兜底（与旧 _build_db_text 等价）
    if not parts:
        for key in ["描述", "详情", "报价", "备注1", "备注2"]:
            v = (row.get(key) or "").strip()
            if v:
                parts.append(v)

    return " | ".join(parts)


def _build_db_text(row: dict) -> str:
    """
    全量缓存使用的文本构建（加权版）。
    与 _build_weighted_text 逻辑相同，保持一致性。
    """
    return _build_weighted_text(row)


# ─────────────────────────────────────────────────────────────────────────────
# 全量缓存（针对整个价目表，category 子集用局部编码，不持久化缓存）
# ─────────────────────────────────────────────────────────────────────────────

_cache: Dict = {
    "mode":        None,
    "db_texts":    [],
    "vectors":     [],
    "idf":         {},
    "row_indices": [],
}


def _ensure_cache(db_rows: List[dict]) -> bool:
    mode = "bge" if _USE_BGE else "tfidf"
    if _cache["mode"] == mode and len(_cache["db_texts"]) == len(db_rows):
        return True

    logger.info(f"[Matcher] 构建全量 {mode.upper()} 缓存，共 {len(db_rows)} 行…")
    texts, indices = [], []
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
        _cache.update({"mode": mode, "db_texts": texts, "vectors": vectors,
                        "idf": {}, "row_indices": indices})
    else:
        vectors, idf = _tfidf_vectors(texts)
        _cache.update({"mode": mode, "db_texts": texts, "vectors": vectors,
                        "idf": idf, "row_indices": indices})

    logger.info(f"[Matcher] 缓存构建完成，有效行: {len(texts)}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 局部编码（针对 category 候选子集）— 核心两阶段匹配逻辑
# ─────────────────────────────────────────────────────────────────────────────

def _search_in_subset(
    query: str,
    subset_rows: List[dict],
    top_k: int,
    min_score: float,
) -> List[Tuple[int, float, dict]]:
    """
    在给定的行子集里做字段加权语义搜索。

    匹配策略（两阶段）：
    ─────────────────────────────────────────────────────────────────────
    Stage A — 详情优先
        仅对"详情"列文本打分。
        若最高分 ≥ _DETAILS_PRIORITY_THRESHOLD，视为"详情完全匹配"，
        直接返回该阶段结果（该行优先级最高）。

    Stage B — 加权组合兜底
        Stage A 未能高分命中时，使用加权文本
        （详情 ×3 权重 + 报价 ×1 权重 + 其余字段 ×1 权重）重新打分，
        保证报价列也被搜索，且详情列权重始终高于报价列。
    ─────────────────────────────────────────────────────────────────────

    返回 [(子集内原始索引, 分数, row_dict), ...]，按分数降序。
    """
    # ── 构建两套文本索引 ────────────────────────────────────────────────────
    details_texts  : List[str] = []   # Stage A: 详情列
    weighted_texts : List[str] = []   # Stage B: 加权组合
    valid_indices  : List[int] = []   # 本子集中的有效行号

    for i, row in enumerate(subset_rows):
        wt = _build_weighted_text(row)
        if not wt.strip():
            continue
        details_texts.append(_build_details_text(row))
        weighted_texts.append(wt)
        valid_indices.append(i)

    if not valid_indices:
        return []

    # ── 辅助：从打分列表中选 top_k ─────────────────────────────────────────
    def _pick(scores_list: List[float]) -> List[Tuple[int, float, dict]]:
        scored = sorted(enumerate(scores_list), key=lambda x: -x[1])[:top_k * 2]
        out: List[Tuple[int, float, dict]] = []
        for li, sc in scored:
            if sc < min_score:
                continue
            orig = valid_indices[li]
            out.append((orig, round(float(sc), 4), subset_rows[orig]))
            if len(out) >= top_k:
                break
        return out

    # ── BGE 路径 ─────────────────────────────────────────────────────────────
    if _USE_BGE:
        try:
            # Stage A: 仅对非空"详情"行打分
            det_pairs = [(li, t) for li, t in enumerate(details_texts) if t.strip()]
            if det_pairs:
                det_li, det_corp = zip(*det_pairs)
                all_vecs = _bge_encode([query] + list(det_corp))
                q_vec    = all_vecs[0]
                det_vecs = all_vecs[1:]
                det_sc   = [sum(a * b for a, b in zip(q_vec, dv)) for dv in det_vecs]

                if max(det_sc) >= _DETAILS_PRIORITY_THRESHOLD:
                    # 将局部得分映射回全 valid_indices 空间（未出现行得分为 0）
                    full_sc = [0.0] * len(valid_indices)
                    for pos, li in enumerate(det_li):
                        full_sc[li] = det_sc[pos]
                    res = _pick(full_sc)
                    if res:
                        logger.debug(
                            f"[Matcher-BGE] Stage A 命中，"
                            f"最高详情分={max(det_sc):.3f}"
                        )
                        return res

            # Stage B: 加权组合
            all_vecs = _bge_encode([query] + weighted_texts)
            q_vec    = all_vecs[0]
            w_vecs   = all_vecs[1:]
            w_sc     = [sum(a * b for a, b in zip(q_vec, dv)) for dv in w_vecs]
            logger.debug("[Matcher-BGE] Stage B 加权组合")
            return _pick(w_sc)

        except Exception as e:
            logger.error(f"[Matcher] BGE 子集编码失败: {e}")
            return []

    # ── TF-IDF 路径 ──────────────────────────────────────────────────────────

    # Stage A: 详情优先
    det_pairs = [(li, t) for li, t in enumerate(details_texts) if t.strip()]
    if det_pairs:
        det_li, det_corp = zip(*det_pairs)
        det_vecs, det_idf = _tfidf_vectors(list(det_corp))
        q_det = _tfidf_encode_query(query, det_idf)
        if q_det:
            det_sc = [_cosine_sparse(q_det, dv) for dv in det_vecs]
            if max(det_sc) >= _DETAILS_PRIORITY_THRESHOLD:
                full_sc = [0.0] * len(valid_indices)
                for pos, li in enumerate(det_li):
                    full_sc[li] = det_sc[pos]
                res = _pick(full_sc)
                if res:
                    logger.debug(
                        f"[Matcher-TFIDF] Stage A 命中，"
                        f"最高详情分={max(det_sc):.3f}"
                    )
                    return res

    # Stage B: 加权组合兜底
    w_vecs, w_idf = _tfidf_vectors(weighted_texts)
    q_w = _tfidf_encode_query(query, w_idf)
    if not q_w:
        return []
    w_sc = [_cosine_sparse(q_w, wv) for wv in w_vecs]
    logger.debug("[Matcher-TFIDF] Stage B 加权组合")
    return _pick(w_sc)


# ─────────────────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────────────────

def find_best_matches(
    customer_desc: str,
    db_rows:       List[dict],
    top_k:         int   = 5,
    min_score:     float = 0.05,
) -> List[Tuple[int, float, dict]]:
    """
    两阶段检索：大类路由 → 字段加权精搜。

    匹配优先级：
      1. 类目路由缩小候选集（category_router）
      2. 详情列精确匹配（Stage A）
      3. 详情×3 + 报价×1 加权组合（Stage B 兜底）

    参数：
        customer_desc : 客户描述文本
        db_rows       : 全量价目表行（FL_DISPLAY 字段的 dict）
        top_k         : 返回最多 top_k 条结果
        min_score     : 最低相似度阈值

    返回：
        [(原始行索引, 相似度分数, row_dict), ...]，按分数降序
    """
    if not customer_desc or not customer_desc.strip() or not db_rows:
        return []

    # ── Stage 1: 大类路由 ────────────────────────────────────────────────────
    try:
        from category_router import route as category_route
        category, candidates, is_fallback = category_route(
            customer_desc, db_rows, fallback_threshold=30
        )
        logger.info(
            f"[Matcher] 类目={category!r}, 候选行={len(candidates)}"
            f"{'(全量退化)' if is_fallback else ''}"
        )
    except ImportError:
        logger.warning("[Matcher] category_router 未找到，跳过分类路由，使用全量搜索")
        category    = "GENERAL"
        candidates  = db_rows
        is_fallback = True

    # ── Stage 2: 字段加权精搜（详情优先 → 加权组合） ─────────────────────────
    if not is_fallback:
        sub_results = _search_in_subset(customer_desc, candidates, top_k, min_score)
        if sub_results:
            # 将子集内索引换算回 db_rows 的原始索引
            id_to_orig = {id(db_rows[j]): j for j in range(len(db_rows))}
            mapped: List[Tuple[int, float, dict]] = []
            for sub_idx, score, row in sub_results:
                orig = id_to_orig.get(
                    id(candidates[sub_idx]) if sub_idx < len(candidates) else id(row)
                )
                if orig is None:
                    orig = next(
                        (k for k, r in enumerate(db_rows) if id(r) == id(row)), sub_idx
                    )
                mapped.append((orig, score, row))
            if mapped:
                return mapped

        logger.info("[Matcher] 子集搜索无结果，退化至全量搜索")

    # ── 全量搜索兜底（使用加权缓存）────────────────────────────────────────────
    if not _ensure_cache(db_rows):
        return []

    mode = _cache["mode"]
    if mode == "bge":
        try:
            q_vec  = _bge_encode([customer_desc])[0]
            scores = [sum(a * b for a, b in zip(q_vec, dv)) for dv in _cache["vectors"]]
        except Exception as e:
            logger.error(f"[Matcher] BGE 全量查询失败: {e}")
            return []
    else:
        q_vec = _tfidf_encode_query(customer_desc, _cache["idf"])
        if not q_vec:
            return []
        scores = [_cosine_sparse(q_vec, dv) for dv in _cache["vectors"]]

    scored = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k * 2]
    results: List[Tuple[int, float, dict]] = []
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
    _cache["mode"]        = None
    _cache["db_texts"]    = []
    _cache["vectors"]     = []
    _cache["idf"]         = {}
    _cache["row_indices"] = []
    logger.info("[Matcher] 缓存已清除")


def get_mode() -> str:
    return "bge" if _USE_BGE else "tfidf"