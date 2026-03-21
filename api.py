"""
api.py — JS-Python 桥接层
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
        """返回 {cols: [...], rows: [[...], ...]}"""
        cols, rows = fetch_fulllist(company_name)
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

    # ── 价格查询（虚拟表方案，格式与 get_price_list 完全相同） ───────────────

    def query_prices(self, items: list, company_name: str) -> dict:
        """
        在后台构建虚拟表，返回与 get_price_list 完全相同的 {cols, rows} 格式。

        固定列：Item NO. | 商品代码 | 客户描述 | 数量 | UOM
        信息列：FL_DISPLAY[0..21]
        价格列：公司专属列 或 High Price + Medium Price
        """
        logging.info(f"[API] query_prices: {len(items)} 条, 公司={company_name!r}")

        # ── 定义虚拟表的列结构 ────────────────────────────────────────────────
        fixed_cols = ["Item NO.", "商品代码", "客户描述", "数量", "UOM"]
        info_cols  = list(FL_DISPLAY[:PRICE_COL_START_IDX])          # 索引 0-21

        col_idx = get_company_col_idx(company_name)
        if col_idx is not None:
            price_cols = [FL_DISPLAY[col_idx]]
        else:
            price_cols = [FL_DISPLAY[23], FL_DISPLAY[24]]            # High / Medium Price

        all_cols = fixed_cols + info_cols + price_cols

        # ── 批量查询数据库，填入虚拟表 ────────────────────────────────────────
        try:
            results = batch_query(items, company_name)
        except Exception as e:
            logging.error(f"[API] batch_query 失败: {e}", exc_info=True)
            return {"cols": all_cols, "rows": []}

        # ── 把每条结果转成与列顺序对齐的列表（同 get_price_list 的 rows 格式）──
        rows = []
        for r in results:
            row = [str(r.get(col) or "") for col in all_cols]
            rows.append(row)

        logging.info(f"[API] 虚拟表构建完成: {len(rows)} 行 × {len(all_cols)} 列")
        return {"cols": all_cols, "rows": rows}

    def query_single(
        self,
        code:    str = "",
        desc:    str = "",
        qty:     str = "",
        item_no: str = "",
        unit:    str = "",
        company: str = "",
    ) -> dict:
        return query_product(
            product_code    = code,
            orig_desc       = desc,
            qty             = qty,
            item_no         = item_no,
            unit            = unit,
            company_col_idx = get_company_col_idx(company),
        )

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
                "Version:0.9\r\n"
                "StartHTML:{sh:08d}\r\nEndHTML:{eh:08d}\r\n"
                "StartFragment:{sf:08d}\r\nEndFragment:{ef:08d}\r\n"
            )
            hdr_len = len(tpl.format(sh=0, eh=0, sf=0, ef=0).encode("utf-8"))
            body    = fragment.encode("utf-8")
            sf      = hdr_len + body.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
            ef      = hdr_len + body.index(b"<!--EndFragment-->")
            data    = (tpl.format(sh=hdr_len, eh=hdr_len + len(body), sf=sf, ef=ef) + fragment).encode("utf-8")
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
        msg.attach(MIMEText(full_html, "html", "utf-8"))
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
                def _status(msg: str):
                    try:
                        self._window.evaluate_js(f"console.log('DB Import:', {json.dumps(msg)})")
                    except Exception:
                        pass
                table_name, row_count = import_excel_to_db(filepath, status_callback=_status)
                success_msg = f"✅ 导入成功！\n表名：{table_name}\n共导入 {row_count} 行数据\n\n请重新点击「价目表」标签以刷新数据。"
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