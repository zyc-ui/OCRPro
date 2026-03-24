"""
RFQ 询价解析工具
- parse_rfq_url(source)  : 供 api.py 调用的函数接口，返回 {cols, rows}
- main()                 : 独立运行时的 CLI 界面（保留原有功能）

依赖安装：pip install requests beautifulsoup4 lxml tabulate
"""
import sys, os, requests
from bs4 import BeautifulSoup
from tabulate import tabulate

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# 目标列定义：(显示名, 表头匹配关键字)
DISPLAY_COLS = [
    ("SevenSeas Code",   "sevenseas"),
    ("Item Description", "description"),
    ("Req Qty",          "req qty"),
    ("UOM",              "uom"),
]


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────────────────────

def load_html(source: str) -> "BeautifulSoup":
    """从 URL 或本地 HTML 文件加载内容，返回 BeautifulSoup 对象。"""
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
    else:
        if not source.startswith("http"):
            source = "https://" + source
        resp = session.get(source, timeout=30)
        resp.raise_for_status()
        html = resp.text
    return BeautifulSoup(html, "lxml")


def find_rfq_table(soup: "BeautifulSoup"):
    """
    找到同时包含 sevenseas / description / qty / uom 关键字的询价表格。
    返回 (table, raw_headers, data_rows)；未找到时返回 (None, None, None)。
    """
    REQUIRED = ["sevenseas", "description", "qty", "uom"]
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        cell_texts = [c.get_text(strip=True) for c in header_cells]
        # 超过 60 字符说明是合并格，跳过
        if any(len(t) > 60 for t in cell_texts):
            continue
        combined = " ".join(t.lower() for t in cell_texts)
        if all(kw in combined for kw in REQUIRED):
            return table, cell_texts, rows[1:]
    return None, None, None


# ─────────────────────────────────────────────────────────────────────────────
# 公开函数接口（供 api.py 调用）
# ─────────────────────────────────────────────────────────────────────────────

def parse_rfq_url(source: str) -> dict:
    """
    解析 SevenSeas 询价链接（URL 或本地 HTML 文件路径）。

    成功返回：
        {
            "cols": ["#", "SevenSeas Code", "Item Description", "Req Qty", "UOM"],
            "rows": [["1", "7912345", "Pump seal kit", "2", "SET"], ...]
        }
    失败抛出 ValueError 或网络异常。
    """
    soup = load_html(source)
    table, raw_headers, data_rows = find_rfq_table(soup)
    if table is None:
        raise ValueError("未找到询价表格，请确认链接或文件正确。")

    # 建立列索引映射
    col_indices = [
        (name, next((i for i, h in enumerate(raw_headers) if kw in h.lower()), -1))
        for name, kw in DISPLAY_COLS
    ]

    parsed_rows: list[dict] = []
    row_num = 1
    for tr in data_rows:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        row_dict = {
            name: (texts[idx] if 0 <= idx < len(texts) else "")
            for name, idx in col_indices
        }
        # 至少 SevenSeas Code 或 Item Description 其中一列非空才算有效行
        if row_dict.get("SevenSeas Code") or row_dict.get("Item Description"):
            row_dict["#"] = str(row_num)
            row_num += 1
            parsed_rows.append(row_dict)

    if not parsed_rows:
        raise ValueError("表格中没有有效数据行。")

    cols = ["#"] + [name for name, _ in DISPLAY_COLS]
    rows = [[r.get(c, "") for c in cols] for r in parsed_rows]
    return {"cols": cols, "rows": rows}


# ─────────────────────────────────────────────────────────────────────────────
# CLI 独立运行入口（原有功能保留）
# ─────────────────────────────────────────────────────────────────────────────

def _parse_and_display_cli(soup: "BeautifulSoup") -> None:
    print("\n[2/2] 定位询价表格...")
    table, raw_headers, data_rows = find_rfq_table(soup)
    if table is None:
        print("[错误] 未找到询价表格，请确认文件/链接正确。")
        sys.exit(1)

    print(f"      ✓ 找到询价表格，表头共 {len(raw_headers)} 列")
    print("\n【原始表头】")
    for i, h in enumerate(raw_headers):
        print(f"  第{i+1:>2}列: {h}")

    col_indices = []
    print("\n【列识别结果】")
    for display_name, keyword in DISPLAY_COLS:
        idx = next((i for i, h in enumerate(raw_headers) if keyword in h.lower()), -1)
        if idx >= 0:
            print(f"  ✓ {display_name:20s} → 第{idx+1}列「{raw_headers[idx]}」")
        else:
            print(f"  ✗ {display_name:20s} → 未找到")
        col_indices.append((display_name, idx))

    display_rows = []
    for tr in data_rows:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        row = {name: (texts[idx] if idx >= 0 and idx < len(texts) else "")
               for name, idx in col_indices}
        if row.get("SevenSeas Code") or row.get("Item Description"):
            display_rows.append(row)

    if not display_rows:
        print("\n[提示] 表格中没有有效数据行。")
        return

    headers = ["#"] + [col[0] for col in DISPLAY_COLS]
    data = [[i] + [r.get(col[0], "") for col in DISPLAY_COLS]
            for i, r in enumerate(display_rows, 1)]

    print(f"\n【询价明细 — 共 {len(display_rows)} 项】")
    print(tabulate(data, headers=headers, tablefmt="rounded_outline",
                   maxcolwidths=[None, None, 50, None, None]))


def main() -> None:
    print("=" * 60)
    print("      RFQ 询价表格解析工具（本地显示）")
    print("=" * 60)
    print("\n支持输入：客户询价链接 或 本地 .htm/.html 文件路径")
    source = input("\n请输入链接或文件路径：").strip().strip('"')
    print(f"\n[1/2] 读取内容：{source}")
    soup = load_html(source)
    _parse_and_display_cli(soup)
    input("\n按 Enter 退出程序。")


if __name__ == "__main__":
    main()