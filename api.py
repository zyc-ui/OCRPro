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

    # ── 价格查询（本地 TF-IDF 模式）────────────────────────────────────────

    def query_prices(self, items: list, company_name: str) -> dict:
        """批量查询，返回 {cols, rows}，描述优先匹配。"""
        logging.info(f"[API] query_prices: {len(items)} 条, 公司={company_name!r}")

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

    # ── 价格查询（向量检索模式 · Seven Seas 专用）───────────────────────────

    def query_prices_vector(self, items: list, company_name: str) -> dict:
        """
        使用 Voyage AI + Qdrant 向量检索进行批量匹配。
        接口格式与 query_prices 完全一致，前端可无缝切换。

        仅在 Seven Seas 公司 + 向量模式开启时由前端调用。
        """
        logging.info(
            f"[API] query_prices_vector: {len(items)} 条, 公司={company_name!r}"
        )
        try:
            from vector_matcher import batch_match
            cols, rows = batch_match(items, company=company_name)
            logging.info(f"[API] 向量匹配完成: {len(rows)} 行 × {len(cols)} 列")
            return {"cols": cols, "rows": rows}
        except ImportError as e:
            msg = f"向量检索依赖未安装，请运行：pip install qdrant-client requests\n详情：{e}"
            logging.error(f"[API] query_prices_vector ImportError: {e}")
            return {"error": msg, "cols": [], "rows": []}
        except Exception as e:
            logging.error(f"[API] query_prices_vector 失败: {e}", exc_info=True)
            return {"error": str(e), "cols": [], "rows": []}

    # ── 价格查询（本地 FAISS + BGE-M3 向量检索）────────────────────────────────

    def query_prices_local_vector(self, items: list, company_name: str) -> dict:
        """
        使用本地 BAAI/bge-m3 + FAISS 向量检索进行批量匹配。
        接口格式与 query_prices / query_prices_vector 完全一致。
        根据客户描述与向量库中的商品描述/详情进行语义+参数精准匹配。
        """
        logging.info(
            f"[API] query_prices_local_vector: {len(items)} 条, 公司={company_name!r}"
        )
        try:
            from local_vector_matcher import batch_match_local_topk
            cols, rows, topk = batch_match_local_topk(items, company=company_name, top_k=20)
            logging.info(f"[API] 本地向量匹配完成: {len(rows)} 行 × {len(cols)} 列")
            return {"cols": cols, "rows": rows, "topk": topk}
        except ImportError as e:
            msg = (
                "本地向量检索依赖未安装，请运行：\n"
                "  pip install sentence-transformers faiss-cpu numpy\n"
                f"详情：{e}"
            )
            logging.error(f"[API] query_prices_local_vector ImportError: {e}")
            return {"error": msg, "cols": [], "rows": [], "topk": []}
        except FileNotFoundError as e:
            msg = str(e)
            logging.error(f"[API] query_prices_local_vector FileNotFoundError: {e}")
            return {"error": msg, "cols": [], "rows": [], "topk": []}
        except Exception as e:
            logging.error(f"[API] query_prices_local_vector 失败: {e}", exc_info=True)
            return {"error": str(e), "cols": [], "rows": [], "topk": []}

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
        import os
        import re
        import tempfile
        import webbrowser

        try:
            from Rfq_quotation_tool import load_html
        except ImportError as e:
            return {"ok": False, "path": "", "error": f"缺少依赖: {e}", "filled": 0}

        try:
            logging.info(f"[API] fill_rfq_prices: url={url!r}, {len(prices)} 条价格")

            soup = load_html(url.strip())

            _ID_PAT = re.compile(
                r'^cdSupplierResp_ctl(\d+)_txtPrice$', re.IGNORECASE
            )

            price_inputs = []
            for tag in soup.find_all('input'):
                tag_id = tag.get('id', '')
                m = _ID_PAT.match(tag_id)
                if m:
                    price_inputs.append((int(m.group(1)), tag))

            if not price_inputs:
                return {
                    "ok": False, "path": "", "filled": 0,
                    "error": (
                        "页面中未找到任何 cdSupplierResp_ctlXX_txtPrice 输入框，"
                        "请确认链接或 HTML 文件正确。"
                    ),
                }

            price_inputs.sort(key=lambda x: x[0])
            logging.info(
                f"[API] fill_rfq_prices: 找到 {len(price_inputs)} 个价格输入框，"
                f"价格列表共 {len(prices)} 条"
            )

            filled = 0
            for idx, (row_no, tag) in enumerate(price_inputs):
                if idx >= len(prices):
                    break

                raw = str(prices[idx]).replace('$', '').strip()
                if not raw:
                    continue

                try:
                    formatted = f"{float(raw):.2f}"
                except ValueError:
                    logging.warning(
                        f"[API] 第 {row_no:02d} 行价格无法解析为数字: {raw!r}，跳过"
                    )
                    continue

                tag['value'] = formatted
                filled += 1
                logging.debug(f"[API]   ctl{row_no:02d} → {formatted}")

            temp_path = os.path.join(tempfile.gettempdir(), 'rfq_filled.html')
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            file_url = 'file:///' + temp_path.replace('\\', '/')
            webbrowser.open(file_url)

            logging.info(
                f"[API] fill_rfq_prices 完成：共填写 {filled} 行，"
                f"已保存至 {temp_path}"
            )
            return {"ok": True, "path": temp_path, "error": "", "filled": filled}

        except Exception as e:
            logging.error(f"[API] fill_rfq_prices 失败: {e}", exc_info=True)
            return {"ok": False, "path": "", "error": str(e), "filled": 0}

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

    # ── 保存结果为 CSV ──────────────────────────────────────────────────────────

    def save_results_csv(self, results: list, cols: list, company: str) -> dict:
        import csv
        import datetime
        import os
        import sys
        try:
            if getattr(sys, "frozen", False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            result_dir = os.path.join(base_dir, "Result")
            os.makedirs(result_dir, exist_ok=True)
            now = datetime.datetime.now()
            safe_company = company.replace(" ", "_").replace("/", "-") if company else "result"
            filename = f"{safe_company}_{now.strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join(result_dir, filename)
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(cols)
                for row in results:
                    writer.writerow([row.get(col, "") for col in cols])
            logging.info(f"[API] save_results_csv: {filepath} ({len(results)} 行)")
            return {"ok": True, "path": filepath}
        except Exception as e:
            logging.error(f"[API] save_results_csv 失败: {e}")
            return {"ok": False, "error": str(e)}

    # ── 数据库更新 ──────────────────────────────────────────────────────────

    def open_db_update(self) -> None:
        def _push_progress(percent: int, message: str, done: bool = False, hide: bool = False):
            if not self._window:
                return
            payload = {
                "percent": int(percent),
                "message": message,
                "done": bool(done),
                "hide": bool(hide),
            }
            js = (
                "window.appState && window.appState._onFullListUpdateProgress && "
                f"window.appState._onFullListUpdateProgress({json.dumps(payload, ensure_ascii=False)});"
            )
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass

        def _pipeline_status(msg: str) -> tuple[int, str]:
            if "阶段一：数据清洗" in msg:
                return 50, "正在清洗数据"
            if "[2/5]" in msg:
                return 58, "正在清洗数据"
            if "[3/5]" in msg:
                return 66, "正在清洗数据"
            if "[4/5]" in msg:
                return 72, "正在清洗数据"
            if "[5/5]" in msg:
                return 78, "正在清洗数据"
            if "阶段二：向量化" in msg:
                return 82, "正在向量化"
            if "[1/4]" in msg:
                return 85, "正在向量化"
            if "[2/4]" in msg:
                return 88, "正在向量化"
            if "[3/4]" in msg:
                return 92, "正在向量化"
            if "[4/4]" in msg:
                return 96, "正在写入向量索引"
            if "向量库已替换" in msg:
                return 99, "正在替换向量库"
            return 80, "正在构建向量库"

        file_result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Excel Files (*.xlsx;*.xls;*.xlsm)", "All files (*.*)")
        )
        if not file_result:
            _push_progress(0, "已取消", done=True, hide=True)
            return
        filepath = file_result[0] if isinstance(file_result, (list, tuple)) else file_result

        def _run():
            import os
            import sys
            try:
                from DatabaseUpdate import import_excel_to_db
                from matcher import clear_cache

                _push_progress(2, "正在读取Excel")

                def _status(msg: str):
                    percent, text = _pipeline_status(msg)
                    _push_progress(percent, text)
                    try:
                        self._window.evaluate_js(
                            f"console.log('DB Import:', {json.dumps(msg)})"
                        )
                    except Exception:
                        pass

                def _import_status(msg: str):
                    _push_progress(10, "正在导入Excel")
                    try:
                        self._window.evaluate_js(
                            f"console.log('DB Import:', {json.dumps(msg)})"
                        )
                    except Exception:
                        pass

                def _import_progress(p: int):
                    overall = 5 + int(max(0, min(100, p)) * 0.40)
                    _push_progress(overall, "正在导入Excel")

                table_name, row_count = import_excel_to_db(
                    filepath,
                    status_callback=_import_status,
                    progress_callback=_import_progress,
                )
                self._pl_rows_cache = []
                self._pl_cols_cache = []
                clear_cache()

                if getattr(sys, "frozen", False):
                    base_dir = os.path.dirname(sys.executable)
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                temp_dir = os.path.join(base_dir, "temp")

                _push_progress(45, "正在构建向量库")
                _status("数据库导入完成，开始构建向量库…")
                from build_product_vectordb import run_pipeline
                vec_result = run_pipeline(
                    input_path=filepath,
                    temp_dir=temp_dir,
                    output_dir=base_dir,
                    status_callback=_status,
                )

                try:
                    from local_vector_matcher import reload_index
                    reload_index()
                except Exception as e:
                    logging.warning(f"[DB Update] 向量库缓存刷新失败: {e}")

                _push_progress(100, "建库完成", done=True)
                success_msg = (
                    f"✅ 导入成功！\n表名：{table_name}\n共导入 {row_count} 行数据\n\n"
                    f"✅ 向量库已更新：{vec_result['vector_count']} 条向量\n"
                    f"中间文件目录：{vec_result['temp_dir']}\n\n"
                    "请重新点击「价目表」标签以刷新数据。"
                )
                self._window.evaluate_js(
                    "window.appState && (window.appState._plLoadedFor = null);"
                    f"alert({json.dumps(success_msg)});"
                )
            except Exception as e:
                error_msg = f"❌ 导入失败：{str(e)}"
                logging.error(f"[DB Update] {error_msg}")
                _push_progress(100, "导入或建库失败", done=True)
                try:
                    self._window.evaluate_js(f"alert({json.dumps(error_msg)})")
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()