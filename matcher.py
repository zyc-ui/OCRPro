"""
matcher.py — 三步描述匹配模块

匹配流程：
  Step 1 · 大类匹配
      从价目表「描述」列动态提取所有大类，
      用 TF-IDF 相似度找到与客户描述最接近的大类，
      筛出该大类的所有候选行。

  Step 2 · 详情列参数命中计数
      把客户描述拆成参数词，
      逐行统计在「详情」列中命中的参数数量，
      命中数最多的行优先返回。

  Step 3 · 报价列兜底
      Step 2 所有候选行命中数均为 0 时（客户描述无具体参数），
      改用 TF-IDF 对「报价」列做整体相似度，
      返回得分最高的行。
"""

import logging
import math
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 分词工具
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """
    技术描述分词：
    - 优先识别「数字+单位」组合（220v, 25mm, 5w, ip65）作为独立 token
    - 普通英文单词正常切分
    - 全部转小写
    """
    text = text.lower()
    # 数字+字母单位组合（如 220v, 25mm, 2.5mm2, ip65）
    num_unit = re.findall(r'\d+\.?\d*\s*[a-z]{1,5}', text)
    # 普通字母词（长度≥2）
    words = re.findall(r'[a-z][a-z0-9]{1,}', text)
    combined = [t.replace(' ', '') for t in num_unit] + words
    # 去重保序
    seen, result = set(), []
    for t in combined:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _tokenize_params(text: str) -> List[str]:
    """
    提取参数词（用于 Step 2 命中计数）：
    更激进地提取数字、单位、颜色、尺寸等关键词，
    过滤掉纯粹的大类名词（避免大类名称本身污染计分）。
    """
    return _tokenize(text)


# ─────────────────────────────────────────────────────────────────────────────
# TF-IDF 工具
# ─────────────────────────────────────────────────────────────────────────────

def _build_tfidf(corpus: List[str]) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    """构建语料库的 TF-IDF 向量组，返回 (向量列表, idf字典)。"""
    n = len(corpus)
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
        vec = {t: (cnt / total) * idf.get(t, 1.0) for t, cnt in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vec = {t: v / norm for t, v in vec.items()}
        vectors.append(vec)

    return vectors, idf


def _encode_query(query: str, idf: Dict[str, float]) -> Dict[str, float]:
    """将查询文本编码为 TF-IDF 向量（使用已有 idf 表）。"""
    tokens = _tokenize(query)
    if not tokens:
        return {}
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = len(tokens)
    vec = {t: (cnt / total) * idf.get(t, 1.0) for t, cnt in tf.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {t: v / norm for t, v in vec.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    return sum(a.get(t, 0.0) * v for t, v in b.items())


# ─────────────────────────────────────────────────────────────────────────────
# 大类索引缓存
# ─────────────────────────────────────────────────────────────────────────────

_cat_cache: Dict = {
    "categories":  [],    # 所有唯一大类名（描述列唯一值）
    "vectors":     [],    # 每个大类的 TF-IDF 向量
    "idf":         {},
    "row_count":   0,
}


def _build_category_index(db_rows: List[dict]) -> bool:
    """
    从价目表「描述」列提取所有唯一大类，构建 TF-IDF 索引。
    描述列格式：「Pilot Lamp xxx」→ 大类 = 完整描述列值（不截断）。
    """
    if _cat_cache["row_count"] == len(db_rows) and _cat_cache["categories"]:
        return True

    seen, categories = set(), []
    for row in db_rows:
        cat = (row.get("描述") or "").strip()
        if cat and cat not in seen:
            seen.add(cat)
            categories.append(cat)

    if not categories:
        logger.warning("[Matcher] 价目表描述列为空，无法建立大类索引")
        return False

    vectors, idf = _build_tfidf(categories)
    _cat_cache.update({
        "categories": categories,
        "vectors":    vectors,
        "idf":        idf,
        "row_count":  len(db_rows),
    })
    logger.info(f"[Matcher] 大类索引构建完成：{len(categories)} 个大类")
    return True


def _find_best_category(query: str, top_n: int = 3) -> List[Tuple[str, float]]:
    """
    返回与查询最匹配的前 top_n 个大类及其得分。
    返回格式：[(大类名, 相似度), ...]
    """
    q_vec = _encode_query(query, _cat_cache["idf"])
    if not q_vec:
        return []

    scored = [
        (_cat_cache["categories"][i], _cosine(q_vec, v))
        for i, v in enumerate(_cat_cache["vectors"])
    ]
    scored.sort(key=lambda x: -x[1])
    return scored[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# Step 2：详情列参数命中计数
# ─────────────────────────────────────────────────────────────────────────────

def _count_param_hits(query_tokens: List[str], details_text: str) -> int:
    """
    统计 query_tokens 中有多少个 token 出现在 details_text 里。
    大小写不敏感，支持部分匹配（token 是 details 子串即可）。
    """
    if not details_text or not query_tokens:
        return 0
    details_lower = details_text.lower()
    return sum(1 for t in query_tokens if t in details_lower)


def _step2_param_match(
    query: str,
    candidate_rows: List[dict],
    top_k: int,
) -> List[Tuple[int, int, dict]]:
    """
    Step 2：对候选行按详情列参数命中数排序。
    返回 [(原始索引, 命中数, row), ...]，命中数 > 0 的行按降序排列。
    """
    query_tokens = _tokenize_params(query)
    scored = []
    for i, row in enumerate(candidate_rows):
        details = (row.get("详情") or "").strip()
        hits = _count_param_hits(query_tokens, details)
        if hits > 0:
            scored.append((i, hits, row))

    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# Step 3：报价列 TF-IDF 兜底
# ─────────────────────────────────────────────────────────────────────────────

def _step3_offer_match(
    query: str,
    candidate_rows: List[dict],
    top_k: int,
    min_score: float,
) -> List[Tuple[int, float, dict]]:
    """
    Step 3：用 TF-IDF 在「报价」列做相似度匹配。
    返回 [(原始索引, 相似度分数, row), ...]。
    """
    offer_texts = [(i, (row.get("报价") or "").strip()) for i, row in enumerate(candidate_rows)]
    valid = [(i, t) for i, t in offer_texts if t]
    if not valid:
        # 报价列也为空，退化到详情列
        valid = [(i, (row.get("详情") or "").strip())
                 for i, row in enumerate(candidate_rows)
                 if (row.get("详情") or "").strip()]
    if not valid:
        return []

    indices, texts = zip(*valid)
    vectors, idf = _build_tfidf(list(texts))
    q_vec = _encode_query(query, idf)
    if not q_vec:
        return []

    scored = sorted(
        [(indices[j], _cosine(q_vec, v)) for j, v in enumerate(vectors)],
        key=lambda x: -x[1]
    )

    result = []
    for orig_idx, score in scored:
        if score < min_score:
            continue
        result.append((orig_idx, round(score, 4), candidate_rows[orig_idx]))
        if len(result) >= top_k:
            break
    return result


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
    三步匹配主入口。

    Step 1：大类匹配（描述列 TF-IDF）→ 筛出同大类候选行
    Step 2：详情列参数命中计数 → 命中多的优先
    Step 3：报价列兜底（Step 2 无命中时启用）

    返回：[(db_rows 原始索引, 分数, row_dict), ...]，按分数/命中数降序
    """
    if not customer_desc or not customer_desc.strip() or not db_rows:
        return []

    # ── Step 1：大类匹配 ──────────────────────────────────────────────────────
    if not _build_category_index(db_rows):
        # 索引构建失败，退化到全量 Step 3
        logger.warning("[Matcher] 大类索引不可用，直接用报价列全量匹配")
        return _step3_offer_match(customer_desc, db_rows, top_k, min_score)

    top_cats = _find_best_category(customer_desc, top_n=3)
    if not top_cats:
        logger.warning("[Matcher] 大类匹配无结果，退化全量")
        return _step3_offer_match(customer_desc, db_rows, top_k, min_score)

    best_cat, best_score = top_cats[0]
    logger.info(
        f"[Matcher] Step1 大类={best_cat!r} 分数={best_score:.3f}"
        + (f"，备选: {top_cats[1][0]!r}({top_cats[1][1]:.3f})" if len(top_cats) > 1 else "")
    )

    # 大类相似度过低时扩大候选（取前3大类合并）
    if best_score < 0.15:
        logger.info("[Matcher] 大类分数低于 0.15，合并前3大类候选行")
        cat_set = {c for c, _ in top_cats}
        candidates = [row for row in db_rows if (row.get("描述") or "").strip() in cat_set]
    else:
        candidates = [row for row in db_rows if (row.get("描述") or "").strip() == best_cat]

    if not candidates:
        logger.info("[Matcher] 候选行为空，退化全量")
        candidates = db_rows

    logger.info(f"[Matcher] Step1 候选行: {len(candidates)} 行")

    # ── Step 2：详情列参数命中计数 ───────────────────────────────────────────
    step2_results = _step2_param_match(customer_desc, candidates, top_k)

    if step2_results:
        logger.info(
            f"[Matcher] Step2 命中 {len(step2_results)} 行，"
            f"最高命中数={step2_results[0][1]}"
        )
        # 将候选子集内索引映射回 db_rows 原始索引
        id_map = {id(row): i for i, row in enumerate(db_rows)}
        mapped = []
        for sub_idx, hits, row in step2_results:
            orig = id_map.get(id(row), sub_idx)
            # 用命中数作为「分数」（整数转 float，保持接口一致）
            mapped.append((orig, float(hits), row))
        return mapped

    # ── Step 3：报价列兜底 ────────────────────────────────────────────────────
    logger.info("[Matcher] Step2 无命中，启用 Step3 报价列兜底")
    step3 = _step3_offer_match(customer_desc, candidates, top_k, min_score)

    if step3:
        id_map = {id(row): i for i, row in enumerate(db_rows)}
        return [(id_map.get(id(row), sub_idx), score, row)
                for sub_idx, score, row in step3]

    # 最终兜底：大类候选行全量退化
    logger.info("[Matcher] Step3 无结果，返回大类首行")
    return [(id_map.get(id(candidates[0]), 0), 0.0, candidates[0])]


def clear_cache():
    """价目表更新后调用，强制重建大类索引。"""
    _cat_cache["categories"] = []
    _cat_cache["vectors"]    = []
    _cat_cache["idf"]        = {}
    _cat_cache["row_count"]  = 0
    logger.info("[Matcher] 缓存已清除")


def get_mode() -> str:
    return "tfidf-3step"