"""
database.py — 数据访问层（DAL）
所有 SQLite 操作集中在此，任何模块不得绕过此文件直接操作数据库。
"""

import logging
import sqlite3
from typing import Dict, List, Optional, Tuple

from config import (
    FL_DB_COLS,
    FL_DISPLAY,
    FL_COMPANY_DISPLAY_TO_IDX,
    PRICE_COL_START_IDX,
    get_db_path,
)


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    """创建并返回新连接；调用方负责关闭。"""
    return sqlite3.connect(get_db_path())


# ─────────────────────────────────────────────────────────────────────────────
# 公司 / 列映射
# ─────────────────────────────────────────────────────────────────────────────

def get_company_col_idx(company_name: str) -> Optional[int]:
    """
    返回公司显示名对应 FL_DISPLAY 的索引（26-33）。
    无匹配或选择 Other 时返回 None。
    """
    if not company_name or company_name.strip().lower() in ("", "other"):
        return None
    return FL_COMPANY_DISPLAY_TO_IDX.get(company_name.strip())


# ─────────────────────────────────────────────────────────────────────────────
# 价目表
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fulllist(company_name: str) -> Tuple[List[str], List[Tuple]]:
    """
    从 FullList 读取全量数据。
    - 信息列：FL_DISPLAY[0..21]
    - 价格列：匹配公司则取该公司列；否则取 High Price + Medium Price
    返回 (display_cols, rows)
    """
    col_idx = get_company_col_idx(company_name)

    if col_idx is not None:
        price_display = [FL_DISPLAY[col_idx]]
        price_db      = [FL_DB_COLS[col_idx]]
    else:
        price_display = [FL_DISPLAY[23], FL_DISPLAY[24]]
        price_db      = [FL_DB_COLS[23],  FL_DB_COLS[24]]

    base_display = FL_DISPLAY[:PRICE_COL_START_IDX]   # 索引 0-21
    base_db      = FL_DB_COLS[:PRICE_COL_START_IDX]

    all_display = base_display + price_display
    all_db      = base_db      + price_db

    sql = 'SELECT {} FROM "FullList" ORDER BY "NO_"'.format(
        ", ".join(f'"{c}"' for c in all_db)
    )

    try:
        con = _conn()
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        con.close()
        return all_display, rows
    except Exception as e:
        logging.error(f"[DB] fetch_fulllist 失败: {e}")
        return all_display, []


def check_fulllist_exists() -> bool:
    """FullList 表是否存在。"""
    try:
        con = _conn()
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='FullList'"
        )
        ok = cur.fetchone() is not None
        con.close()
        return ok
    except Exception as e:
        logging.error(f"[DB] check_fulllist_exists 失败: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 单品查询
# ─────────────────────────────────────────────────────────────────────────────

def _empty_result(
    product_code: str, orig_desc: str, qty: str,
    item_no: str, unit: str,
    u8: str = "", impa: str = "", desc: str = "", price: str = "N/A",
) -> dict:
    """构造空结果行（所有 FL_DISPLAY 字段为空字符串）。"""
    row: dict = {
        "Item NO.": item_no,
        "商品代码": product_code or "",
        "客户描述": orig_desc,
        "数量":     qty,
        "UOM":      unit,
        "价格":     price,
    }
    for name in FL_DISPLAY:
        row[name] = ""
    row["U8代码"]  = u8
    row["IMPA代码"] = impa
    row["描述"]     = desc
    return row


def query_product(
    product_code: str,
    orig_desc: str              = "",
    qty: str                    = "",
    item_no: str                = "",
    unit: str                   = "",
    company_col_idx: Optional[int] = None,
) -> dict:
    """
    按 IMPA / U8 代码查询 FullList。
    优先级：IMPA 精确 → U8 精确 → 模糊匹配。
    返回包含所有 FL_DISPLAY 字段的字典，价格列带 $ 前缀。
    """
    if not product_code:
        return _empty_result(product_code, orig_desc, qty, item_no, unit)

    row = None
    try:
        con = _conn()
        cur = con.cursor()

        cur.execute(
            'SELECT * FROM "FullList" WHERE "IMPA" = ? LIMIT 1',
            (product_code,)
        )
        row = cur.fetchone()

        if not row:
            cur.execute(
                'SELECT * FROM "FullList" WHERE "SEASTAR_U8_CODE" = ? LIMIT 1',
                (product_code,)
            )
            row = cur.fetchone()

        if not row:
            cur.execute(
                'SELECT * FROM "FullList" '
                'WHERE "IMPA" LIKE ? OR "SEASTAR_U8_CODE" LIKE ? LIMIT 1',
                (f"%{product_code}%", f"%{product_code}%")
            )
            row = cur.fetchone()

        con.close()
    except Exception as e:
        logging.error(f"[DB] query_product 错误 {product_code}: {e}")

    if not row:
        return _empty_result(
            product_code, orig_desc, qty, item_no, unit,
            u8="未找到", impa="未找到", desc="未找到匹配的产品"
        )

    result: dict = {
        "Item NO.": item_no,
        "商品代码": product_code,
        "客户描述": orig_desc,
        "数量":     qty,
        "UOM":      unit,
    }
    for i, name in enumerate(FL_DISPLAY):
        val = str(row[i]).strip() if (i < len(row) and row[i] is not None) else ""
        if i >= PRICE_COL_START_IDX and val and not val.startswith("$"):
            val = f"${val}"
        result[name] = val

    # 虚拟 "价格" 键，供前端行颜色判断
    if company_col_idx is not None:
        result["价格"] = result.get(FL_DISPLAY[company_col_idx], "")
    else:
        result["价格"] = (
            result.get(FL_DISPLAY[23], "") or result.get(FL_DISPLAY[24], "")
        )

    return result


def batch_query(items: List[dict], company_name: str = "") -> List[dict]:
    """
    批量查询，顺序与 items 一致。
    每项格式：{item_no, code, desc, qty, unit}
    """
    col_idx = get_company_col_idx(company_name)
    return [
        query_product(
            product_code    = it.get("code", ""),
            orig_desc       = it.get("desc", ""),
            qty             = it.get("qty", ""),
            item_no         = it.get("item_no", ""),
            unit            = it.get("unit", ""),
            company_col_idx = col_idx,
        )
        for it in items
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 全局搜索
# ─────────────────────────────────────────────────────────────────────────────

def search_all_tables(
    keyword: str,
    limit_per_table: int = 500,
) -> Dict[str, Tuple[List[str], List[Tuple]]]:
    """
    在所有用户表中做 LIKE 搜索，单连接遍历。
    返回 {表名: (列名列表, 数据行列表)}
    """
    results: Dict[str, Tuple[List[str], List[Tuple]]] = {}
    if not keyword:
        return results

    try:
        con = _conn()
        cur = con.cursor()
    except Exception as e:
        logging.error(f"[DB] search_all_tables 连接失败: {e}")
        return results

    try:
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]

        for table in tables:
            try:
                cur.execute(f'PRAGMA table_info("{table}")')
                columns = [r[1] for r in cur.fetchall()]
                if not columns:
                    continue

                where  = " OR ".join(f'"{c}" LIKE ?' for c in columns)
                params = [f"%{keyword}%"] * len(columns)
                cur.execute(
                    f'SELECT * FROM "{table}" WHERE {where} LIMIT {limit_per_table}',
                    params
                )
                rows = cur.fetchall()
                if rows:
                    results[table] = (columns, rows)
            except Exception as e:
                logging.error(f"[DB] 搜索表 {table} 失败: {e}")
    finally:
        con.close()

    return results