"""
api.py — JS-Python 桥接层
所有前端 JS 通过 window.pywebview.api.方法名(参数) 调用此类的 public 方法。
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
    """
    pywebview js_api 实例。
    方法命名规则：动词_名词，全小写下划线，与前端 JS 调用名一致。
    """

    def __init__(self):
        self._window: Optional[webview.Window] = None
        self._ocr    = OCREngine()

    def set_window(self, window: webview.Window) -> None:
        """由 app.py 在 webview 启动后注入窗口引用。"""
        self._window = window

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """前端初始化时调用，返回所有静态配置。"""
        return {
            "company_options": COMPANY_OPTIONS,
            "col_widths":      FL_COL_WIDTHS,
            "fl_display":      FL_DISPLAY,
            "db_ok":           check_fulllist_exists(),
        }

    # ── 价目表 ────────────────────────────────────────────────────────────────

    def get_price_list(self, company_name: str) -> dict:
        """
        获取价目表全量数据。
        返回 {cols: [...], rows: [[...], ...]}
        价格列自动加 $ 前缀。
        """
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

    # ── 价格查询 ──────────────────────────────────────────────────────────────

    def query_prices(self, items: list, company_name: str) -> list:
        """
        批量查询价格。
        items: [{item_no, code, desc, qty, unit}, ...]
        返回顺序与 items 一致的结果列表。
        """
        return batch_query(items, company_name)

    def query_single(
        self,
        code:    str = "",
        desc:    str = "",
        qty:     str = "",
        item_no: str = "",
        unit:    str = "",
        company: str = "",
    ) -> dict:
        """查询单个商品（编辑行后重新匹配时使用）。"""
        return query_product(
            product_code    = code,
            orig_desc       = desc,
            qty             = qty,
            item_no         = item_no,
            unit            = unit,
            company_col_idx = get_company_col_idx(company),
        )

    # ── OCR ───────────────────────────────────────────────────────────────────

    def start_ocr(self) -> bool:
        """
        启动 OCR 全屏选区（非阻塞）。
        OCR 完成后前端收到 window.__onOCRResult(items) 回调。
        返回 False 表示 Tesseract 未找到。
        """
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

    # ── 全局搜索 ──────────────────────────────────────────────────────────────

    def global_search(self, keyword: str) -> dict:
        """
        在所有表中搜索关键词。
        返回 {表名: {columns: [...], rows: [[...], ...]}}
        """
        raw = search_all_tables(keyword)
        return {
            table: {"columns": cols, "rows": [list(r) for r in rows]}
            for table, (cols, rows) in raw.items()
        }

    # ── 导出 ──────────────────────────────────────────────────────────────────

    def copy_html_to_clipboard(self, html: str) -> dict:
        """
        将 AG Grid 生成的 HTML 字符串写入 Windows CF_HTML 剪贴板。
        返回 {ok: bool, error: str}
        """
        fragment = (
            "<html>\r\n<body>\r\n<!--StartFragment-->"
            + html
            + "<!--EndFragment-->\r\n</body>\r\n</html>"
        )
        try:
            import win32clipboard

            tpl     = (
                "Version:0.9\r\n"
                "StartHTML:{sh:08d}\r\nEndHTML:{eh:08d}\r\n"
                "StartFragment:{sf:08d}\r\nEndFragment:{ef:08d}\r\n"
            )
            hdr_len = len(tpl.format(sh=0, eh=0, sf=0, ef=0).encode("utf-8"))
            body    = fragment.encode("utf-8")
            sf      = hdr_len + body.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
            ef      = hdr_len + body.index(b"<!--EndFragment-->")
            data    = (
                tpl.format(sh=hdr_len, eh=hdr_len + len(body), sf=sf, ef=ef) + fragment
            ).encode("utf-8")

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            cf = win32clipboard.RegisterClipboardFormat("HTML Format")
            win32clipboard.SetClipboardData(cf, data)
            win32clipboard.CloseClipboard()
            return {"ok": True, "error": ""}
        except ImportError:
            return {"ok": False, "error": "pywin32 未安装，请运行 pip install pywin32"}
        except Exception as e:
            logging.error(f"[Export] 写入剪贴板失败: {e}")
            return {"ok": False, "error": str(e)}

    def save_eml(self, html: str, plain_text: str) -> dict:
        """
        通过 pywebview 原生对话框保存 .eml 文件。
        返回 {ok: bool, path: str, error: str}
        """
        import datetime
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        now       = datetime.datetime.now()
        save_path = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename = f"报价结果_{now.strftime('%Y%m%d_%H%M')}.eml",
            file_types    = ("邮件文件 (*.eml)", "所有文件 (*.*)")
        )
        if not save_path:
            return {"ok": False, "path": "", "error": "cancelled"}

        full_html = (
            '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>\n'
            '<p style="font-family:Arial,sans-serif;font-size:13px;">报价结果如下：</p>\n'
            + html + "\n</body></html>"
        )
        msg            = MIMEMultipart("alternative")
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

    # ── 数据库更新 ────────────────────────────────────────────────────────────

    def open_db_update(self) -> None:
        """在独立 tkinter 线程里弹出 DatabaseUpdate 窗口。"""
        def _run():
            import tkinter as tk
            from DatabaseUpdate import DatabaseUpdateWindow

            root = tk.Tk()
            root.withdraw()
            win  = DatabaseUpdateWindow(root)
            win.win.protocol(
                "WM_DELETE_WINDOW",
                lambda: (win.win.destroy(), root.destroy())
            )
            root.mainloop()

        threading.Thread(target=_run, daemon=True).start()