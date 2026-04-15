"""
vector_matcher.py — 向量检索匹配引擎
基于 Voyage AI（向量化）+ Qdrant（检索）实现语义匹配。

设计原则（来自配置文档）：
  - 客户代码不可信，匹配唯一依据是产品描述文本和技术参数。
  - input_type 必须使用 "query"（对应建库时的 "document"）。
  - Voyage 免费版限流：每分钟最多 1 次批量调用，内置指数退避重试。

公开接口：
  match_by_description(desc, top_k) → list[dict]  单条描述检索
  batch_match(items, company)        → list[dict]  批量，返回与 FL_DISPLAY 对齐的行字典
  payload_to_fl_row(payload, score, company) → dict  Payload → FL_DISPLAY 键名字典
"""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 配置常量
# ─────────────────────────────────────────────────────────────────────────────

VOYAGE_API_KEY  = "pa-pLABwunI04lpfDGg6cyOxmKZ32xymGCah_byZM7hRro"
QDRANT_URL      = "https://5aa93a5a-2e9f-40e3-abf9-2cd7e7bd2afb.us-east-1-1.aws.cloud.qdrant.io"
QDRANT_API_KEY  = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6M2Y0Yzk5ZWQtMDFkYS00MzdlLWIzNWQtMTM2MjNlYzg3ODk1In0"
    ".8hzTHrbM6OTCeuLeRPlSWlKc18-noWEmBi_6fgQM1Fk"
)
COLLECTION_NAME = "seastar_products"

# Qdrant payload 的价格字段 → 公司显示名映射
_COMPANY_PRICE_FIELD: dict[str, str] = {
    "SINWA SGP":      "price_sinwa",
    "Seven Seas":     "price_seven_seas",
    "Wrist Far East": "price_wrist",
    "Anchor Marine":  "price_anchor",
    "RMS Marine":     "price_rms",
    "Fuji Trading":   "price_fuji",
    "Con Lash":       "price_conlash",
}

# 匹配置信度阈值（用于前端颜色提示，由 api.py 传给前端）
SCORE_HIGH   = 0.92
SCORE_MEDIUM = 0.80


# ─────────────────────────────────────────────────────────────────────────────
# Qdrant 客户端（延迟初始化，避免导入时就连接）
# ─────────────────────────────────────────────────────────────────────────────

_qdrant_client = None


def _get_qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
            _qdrant_client = QdrantClient(
                url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30
            )
            logger.info("[VectorMatcher] Qdrant 客户端初始化成功")
        except ImportError:
            raise ImportError(
                "缺少 qdrant-client 库，请运行：pip install qdrant-client"
            )
    return _qdrant_client


# ─────────────────────────────────────────────────────────────────────────────
# Step 1：Voyage AI 向量化
# ─────────────────────────────────────────────────────────────────────────────

def embed_query(text: str, max_retries: int = 5) -> list[float]:
    """
    将单条客户询价描述文本转为 1024 维向量。
    注意：只传描述和参数，不传客户代码。
    """
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {VOYAGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "voyage-large-2-instruct",
                    "input": [text],
                    "input_type": "query",   # 检索时固定用 query
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except requests.exceptions.HTTPError:
            if resp.status_code == 429 and attempt < max_retries - 1:
                delay = 60.0 * (2 ** attempt)
                logger.warning(f"[VectorMatcher] Voyage 限流，等待 {delay:.0f}s 后重试（第 {attempt+1} 次）")
                time.sleep(delay)
            else:
                raise


def embed_batch(texts: list[str], max_retries: int = 5) -> list[list[float]]:
    """
    批量将多条描述文本转为向量（一次 API 调用，更高效）。
    最多 128 条，顺序与输入对应。
    """
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {VOYAGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "voyage-large-2-instruct",
                    "input": texts,
                    "input_type": "query",
                },
                timeout=60,
            )
            resp.raise_for_status()
            return [item["embedding"] for item in resp.json()["data"]]
        except requests.exceptions.HTTPError:
            if resp.status_code == 429 and attempt < max_retries - 1:
                delay = 60.0 * (2 ** attempt)
                logger.warning(f"[VectorMatcher] Voyage 批量限流，等待 {delay:.0f}s 后重试（第 {attempt+1} 次）")
                time.sleep(delay)
            else:
                raise


# ─────────────────────────────────────────────────────────────────────────────
# Step 3：Qdrant 向量检索
# ─────────────────────────────────────────────────────────────────────────────

def search_products(
    query_vector: list[float],
    top_k: int = 10,
    search_filter=None,
) -> list[dict]:
    """
    在 Qdrant 执行向量相似度检索。
    返回 [{"id", "score", "payload"}, ...]，按 score 降序。
    """
    qdrant = _get_qdrant()
    response = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        using="dense",
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )
    return [
        {
            "id":      point.id,
            "score":   round(point.score, 4),
            "payload": point.payload,
        }
        for point in response.points
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 单条描述检索（端到端）
# ─────────────────────────────────────────────────────────────────────────────

def match_by_description(desc: str, top_k: int = 5) -> list[dict]:
    """
    给定客户描述文本，返回 Top K 候选产品（含 score 和 payload）。
    desc 中不应包含客户代码（不可信）。
    """
    if not desc or not desc.strip():
        return []
    query_vector = embed_query(desc.strip())
    return search_products(query_vector, top_k=top_k)


# ─────────────────────────────────────────────────────────────────────────────
# Payload → FL_DISPLAY 兼容行字典
# ─────────────────────────────────────────────────────────────────────────────

def payload_to_fl_row(
    payload: dict,
    score: float,
    company: str = "",
    orig_code: str = "",
    orig_desc: str = "",
    qty: str = "",
    item_no: str = "",
    unit: str = "",
) -> dict:
    """
    将 Qdrant Payload 转换为与 FL_DISPLAY 字段名对齐的行字典。
    保留原始的客户信息字段（Item NO. / 商品代码 / 客户描述 / 数量 / UOM）。

    score 含义：
        ≥ 0.92  → 高置信（绿）
        0.80~0.92 → 中置信（黄）
        < 0.80  → 低置信（红/橙）
    """
    p = payload or {}

    # 价格字段：优先取公司专属价，回退到高档/中档
    price_field  = _COMPANY_PRICE_FIELD.get(company, "")
    company_price = p.get(price_field) if price_field else None

    def _fmt_price(v) -> str:
        if v is None:
            return ""
        try:
            return f"${float(v):.2f}"
        except (ValueError, TypeError):
            return str(v)

    # 置信度标签（方便前端显示）
    if score >= SCORE_HIGH:
        confidence = "⬤ 高"
    elif score >= SCORE_MEDIUM:
        confidence = "◑ 中"
    else:
        confidence = "○ 低"

    row = {
        # ── 客户原始信息（不覆盖）─────────────────────────────
        "Item NO.":  item_no,
        "商品代码":  orig_code,
        "客户描述":  orig_desc,
        "数量":      qty,
        "UOM":       unit,
        # ── 向量匹配产品信息 ──────────────────────────────────
        "Brand Sort":          p.get("brand") or "",
        "NO":                  str(p.get("no") or ""),
        "U8代码":               p.get("internal_code") or "",
        "IMPA代码":             p.get("impa_code") or "",
        "KERGER/IMATECH":      p.get("kerger_code") or "",
        "描述":                 p.get("description") or "",
        "详情":                 p.get("details") or "",
        "报价":                 p.get("offer") or "",
        "备注1":                "",
        "备注2":                "",
        "库存量":               "",
        "Battery/Input":       "",
        "IP Rating":           p.get("ip_rating") or "",
        "Temp Class Gas":      "",
        "Surface Temp Dust":   "",
        "CERT":                "",
        "Packing Dim":         p.get("dimension") or "",
        "Packing Weight(KG)":  "",
        "HS Code":             "",
        "COO":                 "",
        "DATE":                p.get("date_updated") or "",
        "单位":                 p.get("unit") or "",
        # ── 价格 ──────────────────────────────────────────────
        "Cost Price":          "",
        "High Price":          _fmt_price(p.get("high_price")),
        "Medium Price":        _fmt_price(p.get("medium_price")),
        "L GROUP 3":           "",
        "SINWA SGP":           _fmt_price(p.get("price_sinwa")),
        "SSM 7SEA":            "",
        "Seven Seas":          _fmt_price(p.get("price_seven_seas")),
        "Wrist Far East":      _fmt_price(p.get("price_wrist")),
        "Anchor Marine":       _fmt_price(p.get("price_anchor")),
        "RMS Marine":          _fmt_price(p.get("price_rms")),
        "Fuji Trading":        _fmt_price(p.get("price_fuji")),
        "Con Lash":            _fmt_price(p.get("price_conlash")),
        # ── 元信息（仅供调试/提示，不一定显示到列） ───────────
        "价格":                _fmt_price(company_price) if company_price else _fmt_price(p.get("high_price")),
        "_vector_score":       score,
        "_confidence":         confidence,
    }
    return row


# ─────────────────────────────────────────────────────────────────────────────
# 批量匹配（供 api.py 调用）
# ─────────────────────────────────────────────────────────────────────────────

def batch_match(
    items: list[dict],
    company: str = "",
) -> tuple[list[str], list[list]]:
    """
    批量向量匹配，返回 (cols, rows) 与 query_prices() 格式完全一致，
    cols 为列名列表，rows 为二维数组（每行按 cols 顺序排列）。

    items 格式：[{"item_no", "code", "desc", "qty", "unit"}, ...]
    """
    from config import FL_DISPLAY, PRICE_COL_START_IDX

    # 固定前缀列
    fixed_cols = ["Item NO.", "商品代码", "客户描述", "数量", "UOM"]
    info_cols  = list(FL_DISPLAY[:PRICE_COL_START_IDX])

    # 确定价格列（与 query_prices 逻辑一致）
    from config import FL_COMPANY_DISPLAY_TO_IDX
    col_idx = FL_COMPANY_DISPLAY_TO_IDX.get(company)
    if col_idx is not None:
        price_cols = [FL_DISPLAY[col_idx]]
    else:
        price_cols = [FL_DISPLAY[23], FL_DISPLAY[24]]  # High / Medium

    all_cols = fixed_cols + info_cols + price_cols

    # 收集所有有效描述进行批量向量化
    descs = [it.get("desc", "").strip() for it in items]
    valid_indices = [i for i, d in enumerate(descs) if d]

    # 批量调用 Voyage AI（只传有描述的条目）
    vectors: dict[int, list[float]] = {}
    if valid_indices:
        valid_descs = [descs[i] for i in valid_indices]
        logger.info(f"[VectorMatcher] 批量向量化 {len(valid_descs)} 条描述…")
        try:
            vecs = embed_batch(valid_descs)
            for idx, vec in zip(valid_indices, vecs):
                vectors[idx] = vec
        except Exception as e:
            logger.error(f"[VectorMatcher] 批量向量化失败: {e}")
            raise

    rows = []
    for i, item in enumerate(items):
        item_no = item.get("item_no", "")
        code    = item.get("code", "")
        desc    = item.get("desc", "")
        qty     = item.get("qty", "")
        unit    = item.get("unit", "")

        fl_row: Optional[dict] = None
        if i in vectors:
            try:
                candidates = search_products(vectors[i], top_k=1)
                if candidates:
                    best = candidates[0]
                    fl_row = payload_to_fl_row(
                        best["payload"], best["score"],
                        company=company,
                        orig_code=code, orig_desc=desc,
                        qty=qty, item_no=item_no, unit=unit,
                    )
                    logger.debug(
                        f"[VectorMatcher] [{i}] score={best['score']:.4f} "
                        f"→ {best['payload'].get('description','')}"
                    )
            except Exception as e:
                logger.warning(f"[VectorMatcher] 第 {i} 条检索失败: {e}")

        # 构建输出行（与 all_cols 顺序一致）
        row = []
        for col in all_cols:
            if fl_row:
                row.append(str(fl_row.get(col, "") or ""))
            else:
                # 无向量结果：仅保留客户原始字段
                mapping = {
                    "Item NO.": item_no, "商品代码": code,
                    "客户描述": desc, "数量": qty, "UOM": unit,
                }
                row.append(mapping.get(col, ""))
        rows.append(row)

    logger.info(f"[VectorMatcher] 批量匹配完成：{len(rows)} 行")
    return all_cols, rows