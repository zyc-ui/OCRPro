"""
api.py — JS-Python 桥接层
匹配优先级：描述相似度优先，代码精确匹配兜底
"""

import json
import logging
import threading
from typing import List, Optional

import webview

from config import (
    COMPANY_OPTIONS,
    FL_COL_WIDTHS,
    FL_DISPLAY,
    PRICE_COL_START_IDX,
    get_db_path,
)
from database import (
    batch_query,
    check_fulllist_exists,
    fetch_fulllist,
    get_company_col_idx,
    query_product,
    search_all_tables,
)
from ocr_engine import OCREngine


class API:

    def __init__(self):
        self._window: Optional[webview.Window] = None
        self._ocr = OCREngine()
        self._pl_rows_cache: List[dict] = []
        self._pl_cols_cache: List[str]  = []

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # ── 初始化 ──────────────────────────────────────────────────────────────

    def get_config(self) -> dict:
        return {
            "company_options": COMPANY_OPTIONS,
            "col_widths":      FL_COL_WIDTHS,
            "fl_display":      FL_DISPLAY,
            "db_ok":           check_fulllist_exists(),
        }

    # ── 价目表 ──────────────────────────────────────────────────────────────

    def get_price_list(self, company_name: str) -> dict:
        cols, rows = fetch_fulllist(company_name)
        self._pl_cols_cache = cols
        self._pl_rows_cache = [
            {cols[i]: (row[i] or "") for i in range(len(cols))}
            for row in rows
        ]
        try:
            from matcher import clear_cache
            clear_cache()
        except Exception:
            pass
        price_positions = [
            i for i, name in enumerate(cols)
            if name in FL_DISPLAY[PRICE_COL_START_IDX:]
        ]
        result_rows = []
        for row in rows:
            r = list(row)
            for pi in price_positions:
                if pi < len(r) and r[pi]:
                    v = str(r[pi]).strip()
                    if v and not v.startswith("$"):
                        r[pi] = f"${v}"
            result_rows.append(r)
        return {"cols": cols, "rows": result_rows}

    # ── 内部辅助 ────────────────────────────────────────────────────────────

    def _ensure_pl_cache(self, company_name: str):
        if self._pl_rows_cache:
            return
        logging.info("[API] 价目表缓存为空，从数据库加载…")
        try:
            pl_cols, pl_rows = fetch_fulllist(company_name)
            self._pl_cols_cache = pl_cols
            self._pl_rows_cache = [
                {pl_cols[i]: (pl_rows[j][i] or "") for i in range(len(pl_cols))}
                for j in range(len(pl_rows))
            ]
            logging.info(f"[API] 缓存加载完成: {len(self._pl_rows_cache)} 行")
        except Exception as e:
            logging.error(f"[API] 加载缓存失败: {e}")

    def _get_matcher(self):
        try:
            from matcher import find_best_matches, get_mode
            logging.info(f"[API] 匹配器就绪，模式: {get_mode()}")
            return find_best_matches
        except Exception as e:
            logging.warning(f"[API] 匹配器不可用: {e}")
            return None

    def _match_one(self, item_no, code, desc, qty, unit, col_idx, find_best_matches):
        matched_row  = None
        match_method = ""

        if desc and find_best_matches and self._pl_rows_cache:
            try:
                sim_results = find_best_matches(
                    desc, self._pl_rows_cache, top_k=1, min_score=0.1
                )
                if sim_results:
                    _, score, pl_row = sim_results[0]
                    sim_code = pl_row.get("U8代码", "") or pl_row.get("IMPA代码", "")
                    if sim_code:
                        try:
                            r = query_product(
                                product_code    = sim_code,
                                orig_desc       = desc,
                                qty             = qty,
                                item_no         = item_no,
                                unit            = unit,
                                company_col_idx = col_idx,
                            )
                            if r.get("U8代码") not in ("未找到", "", None):
                                matched_row  = r
                                match_method = f"🔍 描述匹配 {score:.0%}"
                        except Exception:
                            pass
                    if matched_row is None:
                        matched_row  = pl_row
                        match_method = f"🔍 描述匹配 {score:.0%}"
            except Exception as e:
                logging.warning(f"[API] 相似度匹配失败: {e}")

        if matched_row is None and code:
            try:
                r = query_product(
                    product_code    = code,
                    orig_desc       = desc,
                    qty             = qty,
                    item_no         = item_no,
                    unit            = unit,
                    company_col_idx = col_idx,
                )
                if r.get("U8代码") not in ("未找到", "", None):
                    matched_row  = r
                    match_method = "✅ 代码精确"
            except Exception as e:
                logging.warning(f"[API] 精确匹配失败 {code}: {e}")

        return matched_row, match_method

    # ── 价格查询（Fix3：已移除"匹配方式"列）────────────────────────────────

    def query_prices(self, items: list, company_name: str) -> dict:
        """批量查询，返回 {cols, rows}，描述优先匹配。"""
        logging.info(f"[API] query_prices: {len(items)} 条, 公司={company_name!r}")

        # Fix3: 去掉 "匹配方式"
        fixed_cols = ["Item NO.", "商品代码", "客户描述", "数量", "UOM"]
        info_cols  = list(FL_DISPLAY[:PRICE_COL_START_IDX])
        col_idx    = get_company_col_idx(company_name)
        price_cols = [FL_DISPLAY[col_idx]] if col_idx is not None else [FL_DISPLAY[23], FL_DISPLAY[24]]
        all_cols   = fixed_cols + info_cols + price_cols

        self._ensure_pl_cache(company_name)
        find_best_matches = self._get_matcher()

        rows = []
        for item in items:
            item_no = item.get("item_no", "")
            code    = item.get("code",    "")
            desc    = item.get("desc",    "")
            qty     = item.get("qty",     "")
            unit    = item.get("unit",    "")

            matched_row, _ = self._match_one(
                item_no, code, desc, qty, unit, col_idx, find_best_matches
            )

            row = []
            for col in all_cols:
                if   col == "Item NO.": row.append(item_no)
                elif col == "商品代码": row.append(code)
                elif col == "客户描述": row.append(desc)
                elif col == "数量":     row.append(qty)
                elif col == "UOM":      row.append(unit)
                elif matched_row:       row.append(str(matched_row.get(col, "") or ""))
                else:                   row.append("")
            rows.append(row)

        logging.info(f"[API] 虚拟表: {len(rows)} 行 × {len(all_cols)} 列")
        return {"cols": all_cols, "rows": rows}

    # ── 单条重新匹配 ─────────────────────────────────────────────────────────

    def query_single_desc_first(
        self,
        code:    str = "",
        desc:    str = "",
        qty:     str = "",
        item_no: str = "",
        unit:    str = "",
        company: str = "",
    ) -> dict:
        col_idx = get_company_col_idx(company)
        self._ensure_pl_cache(company)
        find_best_matches = self._get_matcher()

        matched_row, match_method = self._match_one(
            item_no, code, desc, qty, unit, col_idx, find_best_matches
        )

        if matched_row:
            matched_row["匹配方式"] = match_method
            return matched_row

        result = query_product(
            product_code    = code,
            orig_desc       = desc,
            qty             = qty,
            item_no         = item_no,
            unit            = unit,
            company_col_idx = col_idx,
        )
        result["匹配方式"] = ""
        return result

    # ── 旧接口兼容 ───────────────────────────────────────────────────────────

    def query_single(self, code="", desc="", qty="", item_no="", unit="", company="") -> dict:
        return query_product(
            product_code    = code,
            orig_desc       = desc,
            qty             = qty,
            item_no         = item_no,
            unit            = unit,
            company_col_idx = get_company_col_idx(company),
        )

    # ── RFQ 询价解析 ────────────────────────────────────────────────────────

    def parse_rfq(self, url: str) -> dict:
        try:
            from Rfq_quotation_tool import parse_rfq_url
            result = parse_rfq_url(url.strip())
            logging.info(f"[API] parse_rfq 成功: {len(result.get('rows', []))} 行")
            return result
        except ImportError as e:
            msg = f"缺少依赖库（requests / beautifulsoup4 / lxml），请运行 pip install 安装：{e}"
            logging.error(f"[API] parse_rfq ImportError: {e}")
            return {"error": msg, "cols": [], "rows": []}
        except Exception as e:
            logging.error(f"[API] parse_rfq 失败: {e}")
            return {"error": str(e), "cols": [], "rows": []}

    # ── Fix4: 将查询价格填入 RFQ 表格并在浏览器中打开 ────────────────────────

    def fill_rfq_prices(self, url: str, prices: list) -> dict:
        """
        将查询到的价格按顺序写入 RFQ 表格的 Unit Price 列，
        保存为本地临时 HTML 后用默认浏览器打开。

        参数：
            url    : 原始 RFQ 链接或本地 HTML 文件路径
            prices : 与询价行顺序对应的价格列表（字符串，可含 $ 前缀）

        返回：
            {"ok": True/False, "path": "...", "error": "..."}
        """
        try:
            import os
            import tempfile
            import webbrowser
            from bs4 import NavigableString
            from Rfq_quotation_tool import load_html, find_rfq_table

            logging.info(f"[API] fill_rfq_prices: url={url!r}, {len(prices)} 条价格")

            soup = load_html(url.strip())
            table, raw_headers, data_rows = find_rfq_table(soup)
            if table is None:
                return {"ok": False, "path": "", "error": "未找到询价表格，请确认链接正确"}

            # 找 Unit Price 列索引（不区分大小写）
            unit_price_idx = next(
                (i for i, h in enumerate(raw_headers)
                 if 'unit' in h.lower() and 'price' in h.lower()),
                None
            )
            if unit_price_idx is None:
                # 退而求其次：找单独的 price 列
                unit_price_idx = next(
                    (i for i, h in enumerate(raw_headers) if 'price' in h.lower()),
                    None
                )
            if unit_price_idx is None:
                return {"ok": False, "path": "", "error": "表格中未找到 Unit Price 列"}

            # 过滤有效数据行
            valid_rows = [tr for tr in data_rows if tr.find_all(['td', 'th'])]
            logging.info(f"[API] fill_rfq_prices: 表格有效行={len(valid_rows)}, 价格数={len(prices)}")

            for i, tr in enumerate(valid_rows):
                if i >= len(prices):
                    break
                price_val = str(prices[i]).replace('$', '').strip()
                if not price_val:
                    continue
                cells = tr.find_all(['td', 'th'])
                if unit_price_idx < len(cells):
                    cell = cells[unit_price_idx]
                    cell.clear()
                    cell.append(NavigableString(price_val))

            # 保存到临时文件
            temp_path = os.path.join(tempfile.gettempdir(), 'rfq_filled.html')
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            # 用默认浏览器打开
            file_url = 'file:///' + temp_path.replace('\\', '/')
            webbrowser.open(file_url)
            logging.info(f"[API] fill_rfq_prices 完成，已保存至 {temp_path}")
            return {"ok": True, "path": temp_path, "error": ""}

        except ImportError as e:
            return {"ok": False, "path": "", "error": f"缺少依赖: {e}"}
        except Exception as e:
            logging.error(f"[API] fill_rfq_prices 失败: {e}")
            return {"ok": False, "path": "", "error": str(e)}

    # ── OCR ────────────────────────────────────────────────────────────────

    def start_ocr(self) -> bool:
        def _on_result(items: list) -> None:
            js_items = [
                {"item_no": t[0], "code": t[1], "desc": t[2], "qty": t[3], "unit": t[4]}
                for t in items
            ]
            payload = json.dumps(js_items, ensure_ascii=False)
            if self._window:
                self._window.evaluate_js(
                    f"window.dispatchEvent(new CustomEvent('ocr-result',{{detail:{payload}}}))"
                )
        return self._ocr.start_selection(_on_result)

    # ── 全局搜索 ────────────────────────────────────────────────────────────

    def global_search(self, keyword: str) -> dict:
        raw = search_all_tables(keyword)
        return {
            table: {"columns": cols, "rows": [list(r) for r in rows]}
            for table, (cols, rows) in raw.items()
        }

    # ── 导出 ────────────────────────────────────────────────────────────────

    def copy_html_to_clipboard(self, html: str) -> dict:
        fragment = (
            "<html>\r\n<body>\r\n<!--StartFragment-->"
            + html + "<!--EndFragment-->\r\n</body>\r\n</html>"
        )
        try:
            import win32clipboard
            tpl = (
                "Version:0.9\r\nStartHTML:{sh:08d}\r\nEndHTML:{eh:08d}\r\n"
                "StartFragment:{sf:08d}\r\nEndFragment:{ef:08d}\r\n"
            )
            hdr_len = len(tpl.format(sh=0, eh=0, sf=0, ef=0).encode("utf-8"))
            body    = fragment.encode("utf-8")
            sf      = hdr_len + body.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
            ef      = hdr_len + body.index(b"<!--EndFragment-->")
            data    = (tpl.format(sh=hdr_len, eh=hdr_len+len(body), sf=sf, ef=ef)+fragment).encode("utf-8")
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            cf = win32clipboard.RegisterClipboardFormat("HTML Format")
            win32clipboard.SetClipboardData(cf, data)
            win32clipboard.CloseClipboard()
            return {"ok": True, "error": ""}
        except ImportError:
            return {"ok": False, "error": "pywin32 未安装"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_eml(self, html: str, plain_text: str) -> dict:
        import datetime
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        now = datetime.datetime.now()
        save_path = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=f"报价结果_{now.strftime('%Y%m%d_%H%M')}.eml",
            file_types=("邮件文件 (*.eml)", "所有文件 (*.*)")
        )
        if not save_path:
            return {"ok": False, "path": "", "error": "cancelled"}
        full_html = (
            '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>\n'
            '<p style="font-family:Arial,sans-serif;font-size:13px;">报价结果如下：</p>\n'
            + html + "\n</body></html>"
        )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"报价结果 {now.strftime('%Y-%m-%d')}"
        msg["From"]    = "quotation@company.com"
        msg["To"]      = ""
        msg["Date"]    = now.strftime("%a, %d %b %Y %H:%M:%S +0800")
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(full_html,  "html",  "utf-8"))
        try:
            path = save_path[0] if isinstance(save_path, (tuple, list)) else save_path
            with open(path, "w", encoding="utf-8") as f:
                f.write(msg.as_string())
            return {"ok": True, "path": path, "error": ""}
        except Exception as e:
            return {"ok": False, "path": "", "error": str(e)}

    # ── 数据库更新 ──────────────────────────────────────────────────────────

    def open_db_update(self) -> None:
        file_result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Excel Files (*.xlsx;*.xls;*.xlsm)", "All files (*.*)")
        )
        if not file_result:
            return
        filepath = file_result[0] if isinstance(file_result, (list, tuple)) else file_result

        def _run():
            try:
                from DatabaseUpdate import import_excel_to_db
                from matcher import clear_cache
                def _status(msg: str):
                    try:
                        self._window.evaluate_js(
                            f"console.log('DB Import:', {json.dumps(msg)})"
                        )
                    except Exception:
                        pass
                table_name, row_count = import_excel_to_db(filepath, status_callback=_status)
                self._pl_rows_cache = []
                self._pl_cols_cache = []
                clear_cache()
                success_msg = (f"✅ 导入成功！\n表名：{table_name}\n共导入 {row_count} 行数据\n\n"
                               "请重新点击「价目表」标签以刷新数据。")
                self._window.evaluate_js(
                    "window.appState && (window.appState._plLoadedFor = null);"
                    f"alert({json.dumps(success_msg)});"
                )
            except Exception as e:
                error_msg = f"❌ 导入失败：{str(e)}"
                logging.error(f"[DB Update] {error_msg}")
                try:
                    self._window.evaluate_js(f"alert({json.dumps(error_msg)})")
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()