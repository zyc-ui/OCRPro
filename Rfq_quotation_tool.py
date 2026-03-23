"""
RFQ 询价解析工具（本地显示）
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

def load_html(source):
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        print("      ✓ 本地文件读取成功")
    else:
        if not source.startswith("http"):
            source = "https://" + source
        resp = session.get(source, timeout=30)
        resp.raise_for_status()
        html = resp.text
        print("      ✓ 页面抓取成功")
    return BeautifulSoup(html, "lxml")

def find_rfq_table(soup):
    """
    找到表头行里每个单元格都是独立短文本、
    且同时包含 sevenseas/description/qty/uom 关键字的表格。
    """
    REQUIRED = ["sevenseas", "description", "qty", "uom"]
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        # 关键判断：表头每格文本要短（不是把所有数据塞在一起的合并格）
        cell_texts = [c.get_text(strip=True) for c in header_cells]
        if any(len(t) > 60 for t in cell_texts):   # 超过60字符说明是合并格，跳过
            continue
        combined = " ".join(t.lower() for t in cell_texts)
        if all(kw in combined for kw in REQUIRED):
            return table, cell_texts, rows[1:]
    return None, None, None

def parse_and_display(soup):
    print("\n[2/2] 定位询价表格...")
    table, raw_headers, data_rows = find_rfq_table(soup)
    if table is None:
        print("[错误] 未找到询价表格，请确认文件/链接正确。")
        sys.exit(1)

    print(f"      ✓ 找到询价表格，表头共 {len(raw_headers)} 列")
    print("\n【原始表头】")
    for i, h in enumerate(raw_headers):
        print(f"  第{i+1:>2}列: {h}")

    # 列索引映射
    col_indices = []
    print("\n【列识别结果】")
    for display_name, keyword in DISPLAY_COLS:
        idx = next((i for i, h in enumerate(raw_headers) if keyword in h.lower()), -1)
        if idx >= 0:
            print(f"  ✓ {display_name:20s} → 第{idx+1}列「{raw_headers[idx]}」")
        else:
            print(f"  ✗ {display_name:20s} → 未找到")
        col_indices.append((display_name, idx))

    # 解析数据行
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

def main():
    print("=" * 60)
    print("      RFQ 询价表格解析工具（本地显示）")
    print("=" * 60)
    print("\n支持输入：客户询价链接 或 本地 .htm/.html 文件路径")
    source = input("\n请输入链接或文件路径：").strip().strip('"')
    print(f"\n[1/2] 读取内容：{source}")
    soup = load_html(source)
    parse_and_display(soup)
    input("\n按 Enter 退出程序。")

if __name__ == "__main__":
    main()