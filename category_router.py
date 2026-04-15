"""
category_router.py — 大类路由器（简化版）

原有硬编码规则已废弃，大类匹配改为由 matcher.py 动态从价目表
「描述」列提取并用 TF-IDF 相似度完成。

本文件保留是为了兼容其他模块的 import，不再承担实际匹配逻辑。
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


def classify_query(text: str) -> str:
    """
    保留接口兼容性，实际大类匹配已移至 matcher.py Step1。
    始终返回 GENERAL，让 matcher.py 自行处理。
    """
    return "GENERAL"


def route(
    query: str,
    db_rows: List[dict],
    *,
    fallback_threshold: int = 30,
) -> Tuple[str, List[dict], bool]:
    """
    保留接口兼容性。
    返回全量行，由 matcher.py 内部完成大类筛选。
    """
    return "GENERAL", db_rows, True