import tkinter as tk
from tkinter import ttk, messagebox, font
import pyautogui
import pytesseract
from PIL import ImageGrab, Image
import re
import threading
import os
import sqlite3
import pyperclip
import traceback
import textwrap
from translate import t, set_lang, get_lang
from main import price_list_from_price_tool
from DatabaseUpdate import open_update_window

import sys as _sys, os as _os
import threading
from config import (
    get_db_path, FL_DISPLAY, FL_DB_COLS, FL_COL_WIDTHS,
    FL_COMPANY_DISPLAY_TO_IDX, COMPANY_OPTIONS,
    PRICE_COL_START_IDX, COMPANY_COL_START_IDX,
    BASE_INFO_INDICES, GENERIC_PRICE_INDICES, L_GROUP_3_IDX,
)
# ==================== TESSERACT 路径配置 ====================

def _get_tesseract_path():
    if getattr(_sys, 'frozen', False):
        # PyInstaller onedir 模式：资源在 _internal 子目录下
        base = _os.path.join(_os.path.dirname(_sys.executable), "_internal")
        path = _os.path.join(base, "Tesseract", "tesseract.exe")
        if _os.path.exists(path):
            return path
        # 兜底：直接在 exe 同级找
        return _os.path.join(_os.path.dirname(_sys.executable), "Tesseract", "tesseract.exe")
    return r"E:\Tesseract\tesseract.exe"

TESSERACT_PATH = _get_tesseract_path()
HAS_MAIN_FUNCTIONS = True
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class OCRTool:
    def __init__(self, on_items_recognized=None):
        self.on_items_recognized = on_items_recognized
        self.root = None
        self.selecting = False
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.selection_window = None
        # 添加双击选择回调函数存储
        self.price_tree_select_callback = None
        # 价目表逐行高度标签映射 {item_id: tag_name}
        self._price_item_heights = {}

    def check_tesseract(self):
        try:
            if not os.path.exists(TESSERACT_PATH):
                return False
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def start(self):
        if not self.check_tesseract():
            messagebox.showerror("Tesseract OCR未找到", f"无法找到Tesseract:\n{TESSERACT_PATH}")
            return False
        self.root = tk.Toplevel()
        self.root.withdraw()
        self.root.transient()
        return True

    def start_selection(self):
        self.selection_window = tk.Toplevel()
        self.selection_window.attributes('-fullscreen', True)
        self.selection_window.attributes('-alpha', 0.3)
        self.selection_window.attributes('-topmost', True)
        self.selection_window.configure(bg='gray')

        self.selection_window.bind('<ButtonPress-1>', self.on_press)
        self.selection_window.bind('<B1-Motion>', self.on_drag)
        self.selection_window.bind('<ButtonRelease-1>', self.on_release)
        self.selection_window.bind('<Escape>', self.cancel_selection)

        self.canvas = tk.Canvas(self.selection_window, cursor='cross', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def on_press(self, event):
        self.selecting = True
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y,
                                                 outline='red', width=2, fill='blue', stipple='gray12')

    def on_drag(self, event):
        if self.selecting and self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        if self.selecting:
            self.selecting = False
            left = min(self.start_x, event.x)
            top = min(self.start_y, event.y)
            right = max(self.start_x, event.x)
            bottom = max(self.start_y, event.y)

            self.selection_window.destroy()
            self.selection_window = None

            threading.Thread(target=self.perform_ocr, args=(left, top, right, bottom), daemon=True).start()

    def cancel_selection(self, event=None):
        if self.selection_window:
            self.selection_window.destroy()
            self.selection_window = None
        self.close_app()

    def close_app(self):
        if self.root:
            self.root.destroy()
            self.root = None

    def perform_ocr(self, left, top, right, bottom):
        """执行OCR识别 —— 智能配对（支持任意行数 + 列分离 + 数量提取）"""
        try:
            if right - left < 10 or bottom - top < 10:
                self.close_app()
                return

            screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
            screenshot = screenshot.convert('L')

            screenshot = screenshot.point(lambda x: 0 if x < 128 else 255, '1')

            text = pytesseract.image_to_string(screenshot, lang='eng+chi_sim')
            text = '\n'.join(line.strip() for line in text.splitlines())

            print(f"[OCR原始识别文本]:\n{text}")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            # ★ 新增 37\d{4} 识别
            pattern = r'\b(79\d{4}|33\d{4}|37\d{4})\b'
            seen_codes = set()
            all_codes = []
            same_line_descs = []
            pure_desc_lines = []

            for line in lines:
                match = re.search(pattern, line)
                if match:
                    code = match.group(0)
                    if code not in seen_codes:
                        seen_codes.add(code)
                        all_codes.append(code)
                        after = line[match.end():].strip()
                        same_line_descs.append(after)
                else:
                    pure_desc_lines.append(line)

            print(f"[OCR] 识别到代码: {all_codes}")
            print(f"[OCR] 同行描述: {same_line_descs}")
            print(f"[OCR] 纯描述行: {pure_desc_lines}")

            # 常见单位关键词（大写匹配）
            UNIT_KEYWORDS = {
                'PCS', 'PC', 'SET', 'SETS', 'EA', 'EACH',
                'ROLL', 'ROLLS', 'BOX', 'BOXES', 'PAIR', 'PAIRS',
                'M', 'KG', 'G', 'L', 'LTR', 'LITRE', 'LITRES',
                'LENGTH', 'LOT', 'LOTS', 'NOS', 'NO',
                'UNIT', 'UNITS', 'PKT', 'PKG', 'PACK', 'PACKS',
                'BAG', 'BAGS', 'CAN', 'CANS', 'BTL', 'BOTTLE',
                'MTR', 'MM', 'CM', 'FT', 'INCH',
                'TIN', 'TINS', 'TUBE', 'TUBES',
                'SHEET', 'SHEETS', 'COIL', 'COILS',
            }

            def _extract_qty_unit(txt):
                """从文本末尾提取数量和单位，返回 (clean_text, qty_str, unit_str)。
                支持格式：
                  "BULB LED 10 PCS"   → desc="BULB LED", qty="10", unit="PCS"
                  "BULB LED PCS 10"   → desc="BULB LED", qty="10", unit="PCS"
                  "BULB LED 10"       → desc="BULB LED", qty="10", unit=""
                """
                txt = txt.strip()
                if not txt:
                    return "", "", ""

                # 模式1：末尾是 "数量 单位"（单位与数量之间允许有空格）
                m = re.search(
                    r'(\d+[.,]\d+|\d{1,5})\s+([A-Za-z]{1,8})\s*$', txt)
                if m:
                    qty_str  = m.group(1)
                    unit_str = m.group(2).upper()
                    if unit_str in UNIT_KEYWORDS:
                        desc_part = txt[:m.start()].strip()
                        if desc_part:
                            return desc_part, qty_str, unit_str

                # 模式2：末尾是 "数量"（无单位，单位紧贴数字如 "10PCS" 也尝试拆）
                m1b = re.search(
                    r'(\d+[.,]\d+|\d{1,5})([A-Za-z]{1,8})?\s*$', txt)
                if m1b:
                    qty_str  = m1b.group(1)
                    unit_str = (m1b.group(2) or "").upper()
                    if unit_str and unit_str not in UNIT_KEYWORDS:
                        unit_str = ""
                    desc_part = txt[:m1b.start()].strip()
                    if desc_part:
                        return desc_part, qty_str, unit_str

                # 模式3：末尾是 "单位 数量"（如 "PCS 10"）
                m2 = re.search(
                    r'([A-Za-z]{1,8})\s+(\d+[.,]\d+|\d{1,5})\s*$', txt)
                if m2:
                    unit_str = m2.group(1).upper()
                    qty_str  = m2.group(2)
                    if unit_str in UNIT_KEYWORDS:
                        desc_part = txt[:m2.start()].strip()
                        if desc_part:
                            return desc_part, qty_str, unit_str

                # 兜底：只提取数量
                m3 = re.search(r'(\d+[.,]\d+|\d{1,5})\s*$', txt)
                if m3:
                    desc_part = txt[:m3.start()].strip()
                    if desc_part:
                        return desc_part, m3.group(1), ""
                return txt, "", ""

            # 兼容旧调用（部分地方仍用2元组）
            def _extract_qty(txt):
                d, q, u = _extract_qty_unit(txt)
                return d, q

            def _extract_item_no(line):
                """从行首提取 Item NO.（1-4位数字，可含小数），返回 (item_no_str, rest_of_line)"""
                line = line.strip()
                # 情况1：行首数字后跟分隔符+内容，如 "1. 790001 LED"
                m = re.match(r'^(\d{1,4}(?:[.,]\d+)?)[.\s)\-]+(.+)$', line)
                if m:
                    return m.group(1), m.group(2).strip()
                # 情况2：整行就是一个纯数字（独立行的 Item NO.）
                m2 = re.match(r'^(\d{1,4}(?:[.,]\d+)?)$', line)
                if m2:
                    return m2.group(1), ""
                return "", line

            unique_items = []  # 存储 (item_no, code, desc, qty, unit) 五元组

            # ── 辅助：判断一行是否是独立数量行（纯数字，可含小数点） ──
            def _is_qty_line(line):
                # 同时兼容 10.00 和 24,00（逗号作小数点）
                return bool(re.match(r'^\d+([.,]\d+)?\s*$', line.strip()))

            # ── 把 pure_desc_lines 拆成"描述行"和"独立数量行"两组 ──
            real_desc_lines = [l for l in pure_desc_lines if not _is_qty_line(l)]
            col_qty_lines = [l for l in pure_desc_lines if _is_qty_line(l)]
            print(f"[OCR] 描述行: {real_desc_lines}")
            print(f"[OCR] 独立数量列: {col_qty_lines}")

            if not all_codes:
                # 无代码模式：描述行 + 对应数量配对
                for i, line in enumerate(real_desc_lines):
                    item_no, line_rest = _extract_item_no(line)
                    desc_clean, inline_qty, inline_unit = _extract_qty_unit(line_rest)
                    qty = inline_qty or (col_qty_lines[i] if i < len(col_qty_lines) else "")
                    unit = inline_unit
                    if desc_clean:
                        unique_items.append(("", "", desc_clean, qty, unit))
                print(f"[OCR] 无代码模式，识别到 {len(unique_items)} 行描述")
                self.root.after(0, self.update_results, unique_items)
                return

            # 同行描述须含字母/数字/中文才算有效，过滤逗号等OCR噪声
            same_line_has_desc = any(
                re.search(r'[A-Za-z0-9\u4e00-\u9fff]', d) for d in same_line_descs
            )

            def _get_qty(inline_qty, index):
                """优先取行内数量，否则取独立数量列对应位置"""
                if inline_qty:
                    return inline_qty
                if index < len(col_qty_lines):
                    return col_qty_lines[index]
                return ""

            # 从原始行中提取 Item NO.（按代码在 lines 中的位置反查）
            def _find_item_no_for_code(code):
                for idx, raw_line in enumerate(lines):
                    if code in raw_line:
                        # 先尝试同行提取
                        item_no, _ = _extract_item_no(raw_line)
                        if item_no:
                            return item_no
                        # 向前查最多2行，找独立数字行或 "Item NO. X" 行
                        for offset in range(1, 3):
                            if idx - offset < 0:
                                break
                            prev = lines[idx - offset].strip()
                            # 情况1：纯数字行，如 "3" 或 "3."
                            item_no2, rest2 = _extract_item_no(prev)
                            if item_no2 and not rest2:
                                return item_no2
                            # 情况2："Item NO. 3" 或 "Item No. 3" 格式
                            m_label = re.match(
                                r'[Ii]tem\s*[Nn][Oo]\.?\s*[:\-]?\s*(\d{1,4}(?:[.,]\d+)?)',
                                prev)
                            if m_label:
                                return m_label.group(1)
                            # 情况3：该行有实质内容则停止向前找
                            if len(prev) > 8:
                                break
                return ""

            if not same_line_has_desc and len(real_desc_lines) == len(all_codes):
                # 纯分行模式
                for i, (code, desc) in enumerate(zip(all_codes, real_desc_lines)):
                    desc = re.sub(r'\s+', ' ', desc).strip()
                    desc_clean, inline_qty, inline_unit = _extract_qty_unit(desc)
                    item_no = _find_item_no_for_code(code)
                    unique_items.append((item_no, code, desc_clean,
                                         _get_qty(inline_qty, i), inline_unit))
                print(f"[OCR] 使用分行模式")
            elif same_line_has_desc:
                # 同行模式
                for i, (code, desc) in enumerate(zip(all_codes, same_line_descs)):
                    desc = re.sub(r'\s+', ' ', desc).strip()
                    desc_clean, inline_qty, inline_unit = _extract_qty_unit(desc)
                    if not inline_qty and i < len(col_qty_lines):
                        inline_qty = col_qty_lines[i]
                    item_no = _find_item_no_for_code(code)
                    unique_items.append((item_no, code, desc_clean, inline_qty, inline_unit))
                print(f"[OCR] 使用同行模式")
            elif len(real_desc_lines) > 0:
                # 混合模式
                desc_iter = iter(real_desc_lines)
                for i, (code, same_desc) in enumerate(zip(all_codes, same_line_descs)):
                    if same_desc.strip():
                        desc = re.sub(r'\s+', ' ', same_desc).strip()
                    else:
                        desc = re.sub(r'\s+', ' ', next(desc_iter, "")).strip()
                    desc_clean, inline_qty, inline_unit = _extract_qty_unit(desc)
                    item_no = _find_item_no_for_code(code)
                    unique_items.append((item_no, code, desc_clean,
                                         _get_qty(inline_qty, i), inline_unit))
                print(f"[OCR] 使用混合模式")
            else:
                for i, code in enumerate(all_codes):
                    item_no = _find_item_no_for_code(code)
                    unique_items.append((item_no, code, "", _get_qty("", i), ""))
                print(f"[OCR] 使用兜底模式（仅代码）")

            print(f"[OCR] 最终配对: {unique_items}")
            self.root.after(0, self.update_results, unique_items)

        except Exception as e:
            print(f"OCR错误: {str(e)}")
            self.close_app()

    def update_results(self, items):
        """OCR 完成后回到主线程；若窗口已被销毁则静默退出。"""
        try:
            if self.root and self.root.winfo_exists():
                if self.on_items_recognized:
                    self.root.after(0, lambda: self.on_items_recognized(items))
                self.root.after(100, lambda: self.close_app())
        except tk.TclError:
            pass  # 窗口已销毁，忽略


class PriceQueryTool:
    def __init__(self, root):
        self.root = root
        self.root.title("UMIHOSHI")

        self.font = font.Font(family="Helvetica", size=12)
        self.unit_height = self.font.metrics('linespace')
        self.prev_column_widths = {}

        self.setup_ios_style()

        self.conn = None
        self.cursor = None

        self.company_var = tk.StringVar()
        # 公司下拉选项：Other + 7个公司列
        self.company_options = ["Other"] + list(FL_COMPANY_DISPLAY_TO_IDX.keys())
        self.company_price_col_idx = None  # None = Other
        self.pricing_type = None  # 保留兼容，不再使用
        self.company_price_col_idx = None  # 当前公司对应的 FullList 列索引（25-31），None=默认
        self.product_items = []
        self.query_results = []
        self._results_lock = threading.Lock()  # 保护 query_results 的线程安全
        # column_visibility：索引 0-24 的列，公司列(25-31)由公司选择自动控制
        self.column_visibility = {
            FL_DISPLAY[i]: tk.BooleanVar(value=True) for i in range(25)
        }

        self.suggestion_listbox = None
        self.selected_tree_item = None

        # 需要随语言切换刷新的 widget 引用
        self._lang_widgets: dict = {}
        # 列显示复选框引用 {col_name: Checkbutton widget}
        self._col_checkbuttons: dict = {}

        self.setup_ui()
        self.connect_database()

    def setup_ios_style(self):
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(family="Helvetica", size=11)

        self.root.geometry("1400x780")
        self.root.configure(bg="#f5f5f7")

        style = ttk.Style()
        style.theme_use('clam')

        # ── 主色板（Apple Light） ──
        BG       = "#f5f5f7"
        SURFACE  = "#ffffff"
        BLUE     = "#007aff"
        BLUE_HOV = "#0056cc"
        BORDER   = "#d2d2d7"
        TEXT     = "#1d1d1f"
        SUB      = "#6e6e73"

        # 按钮
        style.configure('Primary.TButton',
                        font=('Helvetica', 11, 'bold'),
                        padding=(10, 5),
                        background=BLUE, foreground="white",
                        borderwidth=0, relief="flat")
        style.map('Primary.TButton',
                  background=[('active', BLUE_HOV)],
                  relief=[('active', 'flat')])

        style.configure('Ghost.TButton',
                        font=('Helvetica', 11),
                        padding=(8, 4),
                        background=SURFACE, foreground=BLUE,
                        borderwidth=1, relief="solid")
        style.map('Ghost.TButton',
                  background=[('active', '#e8f0fe')])

        # 标签
        style.configure('Title.TLabel',
                        font=('Helvetica', 13, 'bold'),
                        foreground=TEXT, background=BG)
        style.configure('Sub.TLabel',
                        font=('Helvetica', 10),
                        foreground=SUB, background=BG)

        # 容器
        style.configure('Card.TFrame',
                        background=SURFACE, relief="flat")
        style.configure('TFrame', background=BG)
        style.configure('TLabelframe',
                        background=BG, relief="flat",
                        borderwidth=0)
        style.configure('TLabelframe.Label',
                        font=('Helvetica', 10, 'bold'),
                        foreground=SUB, background=BG)

        # Treeview
        style.configure('Custom.Treeview',
                        font=('Helvetica', 11),
                        rowheight=self.unit_height,
                        background=SURFACE,
                        fieldbackground=SURFACE,
                        foreground=TEXT,
                        borderwidth=0, relief="flat")
        style.configure('Custom.Treeview.Heading',
                        font=('Helvetica', 10, 'bold'),
                        background="#e8e8ed",
                        foreground=TEXT,
                        relief="flat", borderwidth=0)
        style.map('Custom.Treeview',
                  background=[('selected', '#cce0ff')],
                  foreground=[('selected', TEXT)])

        # Combobox
        style.configure('TCombobox',
                        font=('Helvetica', 11),
                        fieldbackground=SURFACE,
                        background=SURFACE,
                        foreground=TEXT,
                        padding=(6, 4))

        # Checkbutton
        style.configure('TCheckbutton',
                        font=('Helvetica', 10),
                        background=BG, foreground=TEXT)

        # Scrollbar（细条）
        style.configure('Thin.Vertical.TScrollbar',
                        width=6, arrowsize=6,
                        background=BORDER, troughcolor=BG)
        style.configure('Thin.Horizontal.TScrollbar',
                        width=6, arrowsize=6,
                        background=BORDER, troughcolor=BG)

        # 存颜色供 setup_ui 直接用
        self._C = dict(BG=BG, SURFACE=SURFACE, BLUE=BLUE,
                       BORDER=BORDER, TEXT=TEXT, SUB=SUB)

    def create_database_connection(self):
        try:
            conn = sqlite3.connect(get_db_path())  # ← 用 config.get_db_path()
            cursor = conn.cursor()
            return conn, cursor
        except Exception as e:
            print(f"创建数据库连接失败: {str(e)}")
            return None, None

    def connect_database(self):
        try:
            self.conn, self.cursor = self.create_database_connection()
            if self.conn and self.cursor:
                print(f"数据库连接成功: {get_db_path()}")  # ← get_db_path()
                self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='FullList'")
                if not self.cursor.fetchone():
                    messagebox.showwarning("警告", "数据库缺少 FullList 表，请先使用 FullListUpdate 导入数据")
        except Exception as e:
            messagebox.showerror("数据库错误", f"无法连接数据库: {str(e)}\n路径: {get_db_path()}")  # ← get_db_path()

    def setup_ui(self):
        C = self._C
        PAD = 10   # 统一外边距

        # ══════════════════════════════════════════════════════
        # 最外层容器（白底卡片，无标题）
        # ══════════════════════════════════════════════════════
        outer = ttk.Frame(self.root, style='Card.TFrame')
        outer.pack(fill=tk.BOTH, expand=True, padx=PAD, pady=PAD)

        # ── 顶部控制栏（单行，紧凑） ──────────────────────────
        top_bar = tk.Frame(outer, bg=C['SURFACE'], pady=6)
        top_bar.pack(fill=tk.X, padx=PAD)

        # ── 语言切换按钮（最右侧，先 pack RIGHT 才能靠右）────────────────────
        self._lang_btn = tk.Button(
            top_bar, text="EN",
            command=self._toggle_lang,
            font=('Helvetica', 9, 'bold'),
            bg=C['SURFACE'], fg='#007aff',
            relief="solid", bd=1, cursor="hand2",
            padx=5, pady=2,
            activebackground='#e8f0fe', activeforeground='#0056cc',
        )
        self._lang_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # 公司代码标签 + Combobox
        self._lang_widgets['lbl_company'] = tk.Label(
            top_bar, text="公司代码", bg=C['SURFACE'],
            fg=C['SUB'], font=('Helvetica', 10))
        self._lang_widgets['lbl_company'].pack(side=tk.LEFT, padx=(0, 4))

        self.company_entry = ttk.Combobox(top_bar, textvariable=self.company_var,
                                          font=('Helvetica', 11), width=22,
                                          values=self.company_options, state="readonly")
        self.company_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.company_entry.bind("<<ComboboxSelected>>", self._on_company_selected_cb)

        # 分隔线
        tk.Frame(top_bar, bg=C['BORDER'], width=1).pack(side=tk.LEFT, fill=tk.Y,
                                                        padx=8, pady=2)

        # 操作按钮组
        btn_cfg = dict(style='Primary.TButton')
        self.ocr_button = ttk.Button(top_bar, text="OCR识别", command=self.start_ocr, **btn_cfg)
        self.append_ocr_button = ttk.Button(top_bar, text="追加识别", command=self.start_append_ocr, **btn_cfg)
        self.query_button = ttk.Button(top_bar, text="查询价格", command=self.query_prices, **btn_cfg)
        copy_button = ttk.Button(top_bar, text="复制表格", command=self.copy_table_to_clipboard,
                                 style='Ghost.TButton')
        clear_button = ttk.Button(top_bar, text="清空", command=self.clear_all,
                                  style='Ghost.TButton')
        update_db_button = ttk.Button(top_bar, text="FullListUpdate",
                                      command=lambda: open_update_window(self.root),
                                      style='Ghost.TButton')

        # 存引用供刷新用
        self._lang_widgets['btn_ocr'] = self.ocr_button
        self._lang_widgets['btn_append'] = self.append_ocr_button
        self._lang_widgets['btn_query'] = self.query_button
        self._lang_widgets['btn_copy'] = copy_button
        self._lang_widgets['btn_clear'] = clear_button

        for btn in (self.ocr_button, self.append_ocr_button, self.query_button,
                    copy_button, clear_button, update_db_button):
            btn.pack(side=tk.LEFT, padx=3)
        # ── 商品代码提示栏 ──────────────────────────────────────
        info_bar = tk.Frame(outer, bg="#f0f4ff", pady=4)
        info_bar.pack(fill=tk.X, padx=PAD)

        self._lang_widgets['lbl_itemcode'] = tk.Label(
            info_bar, text="商品代码", bg="#f0f4ff",
            fg=C['SUB'], font=('Helvetica', 9, 'bold'))
        self._lang_widgets['lbl_itemcode'].pack(side=tk.LEFT, padx=(6, 4))

        self.codes_label = tk.Label(info_bar, text="未识别到商品代码",
                                    bg="#f0f4ff", fg=C['TEXT'],
                                    font=('Helvetica', 10), anchor='w')
        self.codes_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        # ── 分隔线 ─────────────────────────────────────────────
        tk.Frame(outer, bg=C['BORDER'], height=1).pack(fill=tk.X, padx=PAD, pady=(4, 0))

        # ══════════════════════════════════════════════════════
        # 表格区
        # ══════════════════════════════════════════════════════
        table_outer = tk.Frame(outer, bg=C['SURFACE'])
        table_outer.pack(fill=tk.BOTH, expand=True, padx=PAD, pady=(4, PAD))

        # ── 列显示控制（横向滚动复选框，顶部紧贴表格） ──────────
        col_bar = tk.Frame(table_outer, bg=C['SURFACE'], pady=3)
        col_bar.pack(fill=tk.X)

        self._lang_widgets['lbl_showcols'] = tk.Label(
            col_bar, text="显示列:", bg=C['SURFACE'],
            fg=C['SUB'], font=('Helvetica', 9))
        self._lang_widgets['lbl_showcols'].pack(side=tk.LEFT, padx=(2, 4))

        cb_canvas = tk.Canvas(col_bar, height=22, highlightthickness=0, bg=C['SURFACE'])
        cb_hscroll = ttk.Scrollbar(col_bar, orient="horizontal", command=cb_canvas.xview)
        cb_canvas.configure(xscrollcommand=cb_hscroll.set)
        cb_inner = tk.Frame(cb_canvas, bg=C['SURFACE'])
        cb_canvas.create_window((0, 0), window=cb_inner, anchor="nw")
        cb_inner.bind("<Configure>",
                      lambda e: cb_canvas.configure(scrollregion=cb_canvas.bbox("all")))
        cb_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        cb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for col_name, var in self.column_visibility.items():
            cb = ttk.Checkbutton(cb_inner, text=col_name, variable=var,
                                 command=self.update_table_columns,
                                 style='TCheckbutton')
            cb.pack(side=tk.LEFT, padx=1)
            self._col_checkbuttons[col_name] = cb

        # ── 工具栏（+/- 按钮） ─────────────────────────────────
        tbl_toolbar = tk.Frame(table_outer, bg=C['SURFACE'], pady=2)
        tbl_toolbar.pack(fill=tk.X)

        tk.Frame(tbl_toolbar, bg=C['SURFACE']).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.add_row_btn    = ttk.Button(tbl_toolbar, text="＋", width=3,
                                         command=self.add_blank_row, style='Ghost.TButton')
        self.remove_row_btn = ttk.Button(tbl_toolbar, text="－", width=3,
                                         command=self.remove_selected_row, style='Ghost.TButton')
        self.add_row_btn.pack(side=tk.LEFT, padx=2)
        self.remove_row_btn.pack(side=tk.LEFT, padx=2)

        # ── Treeview ───────────────────────────────────────────
        self.create_table(table_outer)

        # ── KeyRelease 兼容绑定（空方法，保持接口） ────────────
        self.company_entry.bind('<KeyRelease>', self.on_company_search)

    def create_table(self, parent):
        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        fixed_cols = ["行号", "Item NO.", "商品代码", "客户描述", "数量", "UOM"]
        all_columns = fixed_cols + self._get_active_data_cols()

        self.tree = ttk.Treeview(tree_container, columns=all_columns,
                                 show='headings', height=1, style='Custom.Treeview')

        fixed_cfg = {
            "行号": {"width": 45, "anchor": tk.CENTER, "stretch": False},
            "Item NO.": {"width": 65, "anchor": tk.CENTER, "stretch": False},
            "商品代码": {"width": 140, "anchor": tk.CENTER, "stretch": False},
            "客户描述": {"width": 260, "anchor": tk.W, "stretch": False},
            "数量": {"width": 65, "anchor": tk.CENTER, "stretch": False},
            "UOM": {"width": 60, "anchor": tk.CENTER, "stretch": False},
        }
        for col in all_columns:
            self.tree.heading(col, text=col)
            if col in fixed_cfg:
                self.tree.column(col, **fixed_cfg[col])
            else:
                self.tree.column(col, width=FL_COL_WIDTHS.get(col, 110),
                                 anchor=tk.W, stretch=False)

        vsb = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.bind('<Double-1>', self.on_item_double_click)
        self.tree.bind('<ButtonRelease-1>', self.on_item_click)
        self.tree.bind('<ButtonRelease-1>', self.on_header_release, add='+')

        self.tree.tag_configure('evenrow', background='#f0f0f0')
        self.tree.tag_configure('oddrow',  background='#ffffff')
        self.tree.tag_configure('not_found', foreground='red')

        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        self.root.after(100, self.init_column_widths)

    def init_column_widths(self):
        self.prev_column_widths = {col: self.tree.column(col, 'width') for col in self.tree['columns']}

    def on_header_release(self, event):
        """用户松开鼠标时检查列宽是否变化，若有则重算换行和行高"""
        # 只响应表头区域的鼠标释放（列宽拖拽发生在 separator 区域）
        region = self.tree.identify_region(event.x, event.y)
        if region not in ('heading', 'separator'):
            return

        if not hasattr(self, 'prev_column_widths'):
            return

        current_widths = {col: self.tree.column(col, 'width') for col in self.tree['columns']}
        if current_widths != self.prev_column_widths:
            self.prev_column_widths = current_widths
            self.rewrap_all_cells()

    def wrap_text(self, text, col):
        if not text:
            return ""
        no_wrap_columns = ["商品代码", "U8代码", "IMPA代码"]
        if col in no_wrap_columns:
            return str(text)
        text = str(text)

        col_width = 0
        try:
            col_width = self.tree.column(col, 'width')
        except Exception:
            pass

        # 列宽无效时用默认值，避免 chars_per_line 极小导致每行只有几个字
        if col_width <= 0:
            default_widths = {
                "客户描述": 440, "描述": 440, "详细信息": 400,
                "备注": 200, "价格": 100, "单位": 80
            }
            col_width = default_widths.get(col, 150)

        # 用 'W' 测量宽字符，比 '0' 更保守，防止换行后超宽
        avg_char_width = max(1, self.font.measure('W'))
        chars_per_line = max(6, int(col_width / avg_char_width))
        wrapped_lines = textwrap.wrap(text, width=chars_per_line)
        return '\n'.join(wrapped_lines) if wrapped_lines else text

    def _apply_row_height_tag(self, item, row_index, row_data, visible_columns):
        """应用行颜色标签（行高由 update_row_height 统一管理）"""
        bg = '#f0f0f0' if row_index % 2 == 0 else '#ffffff'
        price = row_data.get("价格", "")
        fg = 'red' if (not price or price in ("N/A", "未找到", "查询失败")) else '#212529'
        tag_name = f'rowh_{row_index}'
        self.tree.tag_configure(tag_name, background=bg, foreground=fg)
        self.tree.item(item, tags=(tag_name,))

    def rewrap_all_cells(self):
        children = self.tree.get_children()
        if not children:
            return
        data_cols = self._get_active_data_cols()
        for i, item in enumerate(children):
            if i >= len(self.query_results):
                break
            row_data   = self.query_results[i]
            fixed_vals = [
                i + 1,
                row_data.get("Item NO.", ""),
                row_data.get("商品代码", ""),
                self.wrap_text(row_data.get("客户描述", ""), "客户描述"),
                row_data.get("数量", ""),
                row_data.get("UOM", ""),
            ]
            data_vals = [
                self.wrap_text(str(row_data.get(col, "")), col) for col in data_cols
            ]
            self.tree.item(item, values=fixed_vals + data_vals)
            self._apply_row_height_tag(item, i, row_data, data_cols)
        self.update_row_height()

    def update_row_height(self):
        """扫描最大换行数，更新全局 rowheight（最多显示4行，减少空行感）"""
        max_lines = 1
        for item in self.tree.get_children():
            for val in self.tree.item(item, 'values'):
                if val:
                    n = str(val).count('\n') + 1
                    if n > max_lines:
                        max_lines = n
        max_lines = min(max_lines, 4)          # ★ 最多4行，超出靠滚动条
        new_h = self.unit_height * max_lines + 8
        ttk.Style().configure('Custom.Treeview', rowheight=new_h)

    def on_item_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.selected_tree_item = item

    def add_blank_row(self):
        blank = {"Item NO.": "", "商品代码": "双击选择",
                 "客户描述": "", "数量": "", "UOM": "", "价格": ""}
        for name in FL_DISPLAY:
            blank[name] = ""
        self.query_results.append(blank)
        self.add_row_to_table(blank)
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

    def remove_selected_row(self):
        if not self.selected_tree_item:
            messagebox.showwarning("警告", "请先选择要删除的行")
            return
        if not messagebox.askyesno("确认删除", "确定要删除选中的行吗？"):
            return

        try:
            children = self.tree.get_children()
            index = children.index(self.selected_tree_item)
            self.query_results.pop(index)
            self.tree.delete(self.selected_tree_item)
            self.selected_tree_item = None
            self.update_row_height()
            self.rewrap_all_cells()
        except Exception as e:
            messagebox.showerror("错误", f"删除行时出错: {str(e)}")

    def on_company_search(self, event=None): pass

    def search_companies(self, query): pass

    def show_suggestions(self, companies): pass

    def check_focus(self): pass

    def on_suggestion_navigate(self, event=None): pass

    def _suggestion_select_next(self, event=None): return "break"

    def _suggestion_select_prev(self, event=None): return "break"

    def _suggestion_confirm(self, event=None): return "break"

    def hide_suggestions(self): pass

    def on_company_selected(self, event=None): pass

    def get_pricing_type(self, company_name): pass

    def _on_company_selected_cb(self, event=None):
        """Combobox 选择公司后更新价格列"""
        selected = self.company_var.get().strip()
        if not selected or selected == "Other":
            self.company_price_col_idx = None
            price_info = "价格列: High Price / Medium Price"
        else:
            idx = FL_COMPANY_DISPLAY_TO_IDX.get(selected)
            if idx is not None:
                self.company_price_col_idx = idx
                price_info = f"价格列: {selected}"
            else:
                self.company_price_col_idx = None
                price_info = "价格列: High Price / Medium Price"

        current_text = self.codes_label.cget("text")
        base = current_text.split(" | 已选择")[0]
        self.codes_label.config(text=f"{base} | 已选择公司: {selected} ({price_info})")

        # 如果已有查询结果，刷新价格列显示
        if self.query_results:
            self.update_table_columns()

        if self.product_items:
            self.query_button.config(state=tk.NORMAL)

    def _get_active_data_cols(self):
        """返回当前应显示的数据列名列表（不含前6个固定列）。

        修复说明：
        原代码 range(25) 已包含索引 22-24（Cost/High/Medium Price），
        再次 append 23/24 导致 Treeview 列重复。
        现在将信息列（0-21）与价格列（22-24）分开处理，互不交叠。
        """
        cols = []

        # 1. 信息列（索引 0-21），受用户复选框控制
        for i in range(PRICE_COL_START_IDX):  # range(22) → 0..21
            name = FL_DISPLAY[i]
            if self.column_visibility.get(name, tk.BooleanVar(value=True)).get():
                cols.append(name)

        # 2. 价格列：公司列 与 通用价格列 二选一，不重叠
        if self.company_price_col_idx is not None:
            # 已匹配公司：只追加该公司的专属价格列（索引 26-33）
            cols.append(FL_DISPLAY[self.company_price_col_idx])
        else:
            # 未匹配公司：追加通用价格列 Cost(22) / High(23) / Medium(24)
            for i in range(PRICE_COL_START_IDX, L_GROUP_3_IDX):  # range(22, 25)
                name = FL_DISPLAY[i]
                if self.column_visibility.get(name, tk.BooleanVar(value=True)).get():
                    cols.append(name)

        return cols

    def start_ocr(self):
        self.ocr_tool = OCRTool(on_items_recognized=self.on_items_recognized)
        if self.ocr_tool.start():
            self.root.withdraw()
            self.ocr_tool.start_selection()
            self.root.wait_window(self.ocr_tool.root)
            self.root.deiconify()
            self.root.state('zoomed')  # 识别完成后最大化

    def start_append_ocr(self):
        self.ocr_tool = OCRTool(on_items_recognized=self.on_append_items_recognized)
        if self.ocr_tool.start():
            self.root.withdraw()
            self.ocr_tool.start_selection()
            self.root.wait_window(self.ocr_tool.root)
            self.root.deiconify()
            self.root.state('zoomed')  # 识别完成后最大化

    def on_items_recognized(self, items):
        """主 OCR 回调：保留有代码的项，更新状态栏。"""
        valid_items = []
        for item in items:
            if len(item) == 5:
                item_no, code, desc, qty, unit = item
            else:
                item_no, code, desc, qty, unit = "", item[0], item[1], item[2], ""
            if code:
                valid_items.append((item_no, code, desc, qty, unit))

        self.product_items = valid_items
        items_text = ", ".join([f"{code}: {desc}" for _, code, desc, _, _ in valid_items])
        self.codes_label.config(text=f"Identified: {items_text}")

        # 若已选公司，直接开放查询按钮
        if valid_items and self.company_var.get().strip():
            self.query_button.config(state=tk.NORMAL)

    def on_append_items_recognized(self, items):
        if not items:
            return
        if not self.company_var.get().strip():
            messagebox.showwarning("警告", "请先选择公司以查询新增商品价格")
            added_count = 0
            for item in items:
                if len(item) == 5:
                    item_no, code, desc, qty, unit = item
                else:
                    item_no, code, desc, qty, unit = "", item[0], item[1], item[2], ""
                row_data = {
                    "Item NO.": item_no,
                    "商品代码": code,
                    "客户描述": desc,
                    "数量": qty,
                    "UOM": unit,
                    "U8代码": "未找到" if code else "",
                    "IMPA代码": "未找到" if code else "",
                    "描述": "未找到匹配的产品" if code else "",
                    "价格": "N/A"
                }
                self.query_results.append(row_data)
                self.add_row_to_table(row_data)
                added_count += 1
            children = self.tree.get_children()
            if children:
                self.tree.see(children[-1])
            current_text = self.codes_label.cget("text")
            new_items_text = ", ".join([
                f"{item[1] if len(item) == 5 else item[0]}: {item[2] if len(item) == 5 else item[1]}"
                for item in items])
            if current_text == "未识别到商品代码":
                self.codes_label.config(text=f"追加识别到商品: {new_items_text}")
            else:
                self.codes_label.config(text=f"{current_text} | 追加识别到商品: {new_items_text}")
            return

        self.root.config(cursor="wait")
        self.append_ocr_button.config(state=tk.DISABLED)
        threading.Thread(target=self.append_query_thread, args=(items,), daemon=True).start()

    def append_query_thread(self, items):
        conn, cursor = None, None
        try:
            conn, cursor = self.create_database_connection()
            if not conn or not cursor:
                self.root.after(0, lambda: messagebox.showerror("错误", "无法创建数据库连接"))
                return

            company_name = self.company_var.get().replace('\xa0', ' ')
            added_count = 0
            for item in items:
                if len(item) == 5:
                    item_no, code, orig_desc, qty, unit = item
                else:
                    item_no, code, orig_desc, qty, unit = "", item[0], item[1], item[2], ""
                result = self.query_product_price_in_thread(
                    code, orig_desc, qty, cursor, item_no=item_no, unit=unit)
                if result:
                    self.query_results.append(result)
                    self.root.after(0, self.add_row_to_table, result)
                    added_count += 1

            self.root.after(0, lambda: self.root.config(cursor=""))
            self.root.after(0, lambda: self.append_ocr_button.config(state=tk.NORMAL))
            self.root.after(0, self.scroll_to_bottom)
            self.root.after(0, self.update_codes_label_after_append, items)

        except Exception as e:
            self.root.after(0, lambda: self.root.config(cursor=""))
            self.root.after(0, lambda: self.append_ocr_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: messagebox.showerror("错误", f"追加查询过程中出错: {str(e)}"))
        finally:
            if conn:
                conn.close()

    def scroll_to_bottom(self):
        children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

    def update_codes_label_after_append(self, items):
        current_text = self.codes_label.cget("text")
        new_items_text = ", ".join([
            f"{(item[1] if len(item) == 5 else item[0]) or '(描述)'}: "
            f"{item[2] if len(item) == 5 else item[1]}"
            for item in items])
        if current_text == "未识别到商品代码":
            self.codes_label.config(text=f"追加识别到商品: {new_items_text}")
        else:
            self.codes_label.config(text=f"{current_text} | 追加识别到商品: {new_items_text}")

    def query_prices(self):
        if not self.company_var.get():
            messagebox.showwarning("警告", "请先选择公司")
            return
        if not self.product_items:
            messagebox.showwarning("警告", "请先识别商品代码")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.query_results = []

        self.root.config(cursor="wait")
        self.query_button.config(state=tk.DISABLED)
        threading.Thread(target=self.query_prices_thread, daemon=True).start()

    def query_prices_thread(self):
        conn, cursor = None, None
        try:
            conn, cursor = self.create_database_connection()
            if not conn or not cursor:
                self.root.after(0, lambda: messagebox.showerror("错误", "无法创建数据库连接"))
                return

            company_name = self.company_var.get().replace('\xa0', ' ')
            self.query_results = []
            self.root.after(0, self.clear_table)

            found_count = 0
            not_found_count = 0
            for item in self.product_items:
                if len(item) == 5:
                    item_no, code, orig_desc, qty, unit = item
                else:
                    item_no, code, orig_desc, qty, unit = "", item[0], item[1], item[2], ""
                result = self.query_product_price_in_thread(
                    code, orig_desc, qty, cursor, item_no=item_no, unit=unit)
                # result 现在始终不为 None（有兜底逻辑），直接追加
                if result is not None:
                    self.query_results.append(result)
                    self.root.after(0, self.add_row_to_table, result)
                    if result.get("价格") not in ("N/A", "查询失败", "") and result.get("U8代码") != "未找到":
                        found_count += 1
                    else:
                        not_found_count += 1

            self.root.after(0, lambda: self.root.config(cursor=""))
            self.root.after(0, lambda: self.query_button.config(state=tk.NORMAL))

            total = found_count + not_found_count
            if total > 0:
                msg = f"查询完成，共 {total} 个商品"
                if found_count > 0:
                    msg += f"，其中 {found_count} 个找到价格"
                if not_found_count > 0:
                    msg += f"，{not_found_count} 个未找到或查询失败"
                self.root.after(0, lambda: messagebox.showinfo("完成", msg))
            else:
                self.root.after(0, lambda: messagebox.showinfo("完成", "查询完成，但未找到任何匹配的产品"))
        except Exception as e:
            self.root.after(0, lambda: self.root.config(cursor=""))
            self.root.after(0, lambda: self.query_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: messagebox.showerror("错误", f"查询过程中出错: {str(e)}"))
        finally:
            if conn:
                conn.close()

    # ==================== 核心修复：补全所有字段的查询，带降级兜底 ====================
    def query_product_price_in_thread(self, product_code, orig_desc, qty, cursor,
                                       item_no="", unit=""):
        """查询 FullList，匹配 IMPA 或 U8 代码，返回完整行数据"""
        # 空结果模板
        def _empty_row(u8="", impa="", desc="", price_tag="N/A"):
            r = {"Item NO.": item_no, "商品代码": product_code or "",
                 "客户描述": orig_desc, "数量": qty, "UOM": unit, "价格": price_tag}
            for i, name in enumerate(FL_DISPLAY):
                r[name] = ""
            r["U8代码"]  = u8
            r["IMPA代码"] = impa
            r["描述"]     = desc
            return r

        if not product_code:
            return _empty_row()

        row = None
        try:
            # 1. IMPA 精确匹配
            cursor.execute('SELECT * FROM "FullList" WHERE "IMPA" = ? LIMIT 1',
                           (product_code,))
            row = cursor.fetchone()
            # 2. U8 精确匹配
            if not row:
                cursor.execute('SELECT * FROM "FullList" WHERE "SEASTAR_U8_CODE" = ? LIMIT 1',
                               (product_code,))
                row = cursor.fetchone()
            # 3. 模糊匹配
            if not row:
                cursor.execute(
                    'SELECT * FROM "FullList" WHERE "IMPA" LIKE ? OR "SEASTAR_U8_CODE" LIKE ? LIMIT 1',
                    (f"%{product_code}%", f"%{product_code}%"))
                row = cursor.fetchone()
        except Exception as e:
            print(f"[查询错误] {product_code}: {e}")

        if not row:
            return _empty_row("未找到", "未找到", "未找到匹配的产品")

        # 构建结果 dict
        result = {"Item NO.": item_no, "商品代码": product_code,
                  "客户描述": orig_desc, "数量": qty, "UOM": unit}
        for i, display_name in enumerate(FL_DISPLAY):
            val = str(row[i]).strip() if (i < len(row) and row[i] is not None) else ""
            # 价格列（索引 22-31）加 $ 前缀
            if i >= PRICE_COL_START_IDX and val and not val.startswith('$'):
                val = f"${val}"
            result[display_name] = val

        # 虚拟 "价格" 键供行颜色判断使用
        col_idx = self.company_price_col_idx
        if col_idx is not None:
            result["价格"] = result.get(FL_DISPLAY[col_idx], "")
        else:
            result["价格"] = result.get(FL_DISPLAY[23], "") or result.get(FL_DISPLAY[24], "")

        return result

    def clear_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def add_row_to_table(self, row_data):
        try:
            data_cols = self._get_active_data_cols()
            row_index  = len(self.tree.get_children())
            fixed_vals = [
                row_index + 1,
                row_data.get("Item NO.", ""),
                row_data.get("商品代码", ""),
                self.wrap_text(row_data.get("客户描述", ""), "客户描述"),
                row_data.get("数量", ""),
                row_data.get("UOM", ""),
            ]
            data_vals = [
                self.wrap_text(str(row_data.get(col, "")), col) for col in data_cols
            ]
            item_id = self.tree.insert("", tk.END, values=fixed_vals + data_vals)
            self._apply_row_height_tag(item_id, row_index, row_data, data_cols)
            self.update_row_height()
        except Exception as e:
            print(f"添加行到表格时出错: {str(e)}")

    def update_table_columns(self):
        """复选框变化或公司切换时重建表格列"""
        fixed_cols = ["行号", "Item NO.", "商品代码", "客户描述", "数量", "UOM"]
        data_cols = self._get_active_data_cols()
        all_columns = fixed_cols + data_cols

        self.tree.config(columns=all_columns)

        fixed_cfg = {
            "行号": {"width": 45, "anchor": tk.CENTER, "stretch": False},
            "Item NO.": {"width": 65, "anchor": tk.CENTER, "stretch": False},
            "商品代码": {"width": 140, "anchor": tk.CENTER, "stretch": False},
            "客户描述": {"width": 260, "anchor": tk.W, "stretch": False},
            "数量": {"width": 65, "anchor": tk.CENTER, "stretch": False},
            "UOM": {"width": 60, "anchor": tk.CENTER, "stretch": False},
        }
        for col in all_columns:
            self.tree.heading(col, text=col)
            if col in fixed_cfg:
                self.tree.column(col, **fixed_cfg[col])
            else:
                self.tree.column(col, width=FL_COL_WIDTHS.get(col, 110),
                                 anchor=tk.W, stretch=False)

        for item in self.tree.get_children():
            self.tree.delete(item)
        for row_data in self.query_results:
            self.add_row_to_table(row_data)

        self.selected_tree_item = None

    def on_item_double_click(self, event):
        try:
            item = self.tree.identify_row(event.y)
            if not item:
                return
            column = self.tree.identify_column(event.x)
            if column == '#0':
                return

            col_index = int(column[1:]) - 1
            visible_columns = self.tree['columns']  # 含"行号"在内
            if col_index >= len(visible_columns):
                return
            col_name = visible_columns[col_index]

            self.selected_tree_item = item
            children = self.tree.get_children()
            index = children.index(item)
            row_data = self.query_results[index]

            # 前三列（行号、商品代码、客户描述）双击进入编辑；其余列跳转价目表
            if col_name in ["行号", "商品代码", "客户描述", "数量"]:
                if col_name in ["商品代码", "客户描述", "数量"]:
                    self.edit_original_columns(index, row_data)
                return

            # ---------- 跳转价目表 ----------
            search_keyword = row_data.get("U8代码", "")
            if not search_keyword or search_keyword in ["双击选择", "未找到"]:
                search_keyword = row_data.get("商品代码", "")

            company_name = self.company_var.get().strip()
            if not company_name:
                messagebox.showinfo("提示", "请先选择公司以查看详细价目表")
                return

            def price_tree_callback(selected_data):
                try:
                    if not self.selected_tree_item:
                        return
                    children = self.tree.get_children()
                    idx      = children.index(self.selected_tree_item)
                    old_row  = self.query_results[idx]

                    # 优先用 U8代码，其次 IMPA代码，都没有时用原商品代码
                    u8_from_ss   = (selected_data.get("U8代码", "")
                                    or selected_data.get("SS_U8_Code", "")).strip()
                    impa_from_ss = (selected_data.get("IMPA代码", "")
                                    or selected_data.get("SS_IMPA_Code", "")).strip()
                    query_code   = u8_from_ss or impa_from_ss or old_row.get("商品代码", "")

                    def _requote():
                        rebuilt = None

                        # ── 只有价目表返回了有效的 U8 或 IMPA 才尝试数据库查询 ──
                        # 若两者都为空，说明价目表该行本身没有代码，直接走直填路径
                        has_valid_code = bool(u8_from_ss or impa_from_ss)
                        if has_valid_code:
                            conn2, cur2 = self.create_database_connection()
                            if conn2 and cur2:
                                result = self.query_product_price_in_thread(
                                    query_code,
                                    old_row.get("客户描述", ""),
                                    old_row.get("数量", ""),
                                    cur2
                                )
                                conn2.close()
                                # 查到有效结果（U8/IMPA不是"未找到"）才使用
                                if result and result.get("U8代码") not in ("未找到", ""):
                                    rebuilt = result

                        # ── 数据库未命中：直接把价目表返回的数据填入 ──
                        if rebuilt is None:
                            rebuilt = dict(old_row)   # 保留原始行作为基础
                            # 把 selected_data（FL_DISPLAY 键名）逐字段覆盖
                            for key, val in selected_data.items():
                                if key not in ("商品代码", "客户描述", "数量"):
                                    rebuilt[key] = val
                            # 补充 "价格" 虚拟键（供行颜色判断）
                            price_val = (
                                rebuilt.get("High Price", "")
                                or rebuilt.get("Cost Price", "")
                                or rebuilt.get("SINWA SGP", "")
                            )
                            rebuilt["价格"] = price_val

                        # 保留原始客户信息
                        rebuilt["商品代码"] = old_row.get("商品代码", "")
                        rebuilt["客户描述"] = old_row.get("客户描述", "")
                        rebuilt["数量"]     = old_row.get("数量", "")

                        self.query_results[idx] = rebuilt
                        self.root.after(0, lambda: self._refresh_row_display(idx, rebuilt))
                        self.root.after(0, lambda: setattr(self, 'selected_tree_item', None))

                    threading.Thread(target=_requote, daemon=True).start()
                except Exception as e:
                    print(f"更新行数据失败: {str(e)}")

            # 提取关键词列表：商品代码 + 客户描述 按空格分割
            _code_text = row_data.get("商品代码", "")
            _desc_text = row_data.get("客户描述", "")
            _combined = f"{_code_text} {_desc_text}"
            _seen_kw = set()
            keyword_list = []
            for _w in _combined.split():
                _w = _w.strip()
                if len(_w) > 1 and _w.upper() not in _seen_kw:
                    _seen_kw.add(_w.upper())
                    keyword_list.append(_w)

            if HAS_MAIN_FUNCTIONS:
                try:
                    price_list_from_price_tool(company_name, price_tree_callback,
                                               search_keyword, keyword_list=keyword_list,
                                               customer_code=_code_text,
                                               customer_desc=_desc_text)
                except Exception as e:
                    print(f"调用价目表功能失败: {str(e)}")

        except Exception as e:
            messagebox.showerror("错误", f"处理双击事件时出错: {str(e)}")

    def edit_original_columns(self, index, row_data):
        edit_window = tk.Toplevel(self.root)
        edit_window.title("编辑商品代码 / 客户描述 / 数量")
        edit_window.geometry("700x520")
        edit_window.resizable(False, False)

        # Item NO.
        item_no_var = tk.StringVar(value=row_data.get("Item NO.", ""))
        tk.Label(edit_window, text="Item NO.:").grid(row=0, column=0, padx=10, pady=6, sticky='e')
        tk.Entry(edit_window, textvariable=item_no_var, width=20).grid(row=0, column=1, padx=10, pady=6, sticky='w')

        # 商品代码
        code_var = tk.StringVar(value=row_data.get("商品代码", ""))
        tk.Label(edit_window, text="商品代码:").grid(row=1, column=0, padx=10, pady=6, sticky='e')
        tk.Entry(edit_window, textvariable=code_var, width=40).grid(row=1, column=1, padx=10, pady=6, sticky='w')

        # 客户描述
        tk.Label(edit_window, text="客户描述:").grid(row=2, column=0, padx=10, pady=6, sticky='ne')
        desc_frame = tk.Frame(edit_window)
        desc_frame.grid(row=2, column=1, padx=10, pady=6, sticky='nsew')
        desc_scrollbar = tk.Scrollbar(desc_frame)
        desc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        desc_text = tk.Text(desc_frame, width=40, height=8, wrap='word',
                            yscrollcommand=desc_scrollbar.set)
        desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_scrollbar.config(command=desc_text.yview)
        desc_text.insert(tk.END, row_data.get("客户描述", ""))

        # 数量
        qty_var = tk.StringVar(value=row_data.get("数量", ""))
        tk.Label(edit_window, text="数量:").grid(row=3, column=0, padx=10, pady=6, sticky='e')
        tk.Entry(edit_window, textvariable=qty_var, width=20).grid(row=3, column=1, padx=10, pady=6, sticky='w')

        # 单位
        unit_var = tk.StringVar(value=row_data.get("UOM", ""))
        tk.Label(edit_window, text="UOM:").grid(row=4, column=0, padx=10, pady=6, sticky='e')
        tk.Entry(edit_window, textvariable=unit_var, width=20).grid(row=4, column=1, padx=10, pady=6, sticky='w')

        # 按钮行
        btn_frame = tk.Frame(edit_window)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=14)

        def _apply_new_data():
            """把编辑窗口的值写回 row_data 并刷新表格显示，返回新值"""
            new_item_no = item_no_var.get().strip()
            new_code = code_var.get().strip()
            new_desc = desc_text.get("1.0", tk.END).strip()
            new_qty = qty_var.get().strip()
            new_unit = unit_var.get().strip()
            row_data["Item NO."] = new_item_no
            row_data["商品代码"] = new_code
            row_data["客户描述"] = new_desc
            row_data["数量"] = new_qty
            row_data["UOM"] = new_unit
            self.query_results[index] = row_data
            return new_code, new_desc, new_qty

        def save_changes():
            _apply_new_data()
            self._refresh_row_display(index, row_data)
            edit_window.destroy()

        def do_requote():
            """保存修改后重新按商品代码查询，更新整行数据"""
            new_code, new_desc, new_qty = _apply_new_data()
            # 读取当前编辑窗口中的 Item NO. 和 UOM
            cur_item_no = item_no_var.get().strip()
            cur_unit    = unit_var.get().strip()
            edit_window.destroy()
            if not new_code:
                messagebox.showwarning("NOTICE", "IMPA is null! Identify again")
                return
            if not self.company_var.get().strip():
                messagebox.showwarning("NOTICE", "Please select Company first")
                return
            self.root.config(cursor="wait")

            def _thread():
                try:
                    conn, cursor = self.create_database_connection()
                    if conn and cursor:
                        result = self.query_product_price_in_thread(
                            new_code, new_desc, new_qty, cursor,
                            item_no=cur_item_no, unit=cur_unit)
                        conn.close()
                        if result:
                            self.query_results[index] = result
                            self.root.after(0, lambda: self._refresh_row_display(index, result))
                        else:
                            self.root.after(0, lambda: messagebox.showwarning("提示", "未找到匹配商品"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("错误", "无法创建数据库连接"))
                except Exception as e:
                    err_msg = str(e)
                    print(f"[识别线程错误] {err_msg}\n{traceback.format_exc()}")
                    self.root.after(0, lambda: messagebox.showerror("查询出错", f"识别时发生错误：\n{err_msg}"))
                finally:
                    # 无论成功、失败、异常，都必须恢复光标
                    self.root.after(0, lambda: self.root.config(cursor=""))

            threading.Thread(target=_thread, daemon=True).start()

        tk.Button(btn_frame, text="OK", command=save_changes,
                  width=10, relief="flat").pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="Match", command=do_requote,
                  width=10, bg="#007aff", fg="white", relief="flat").pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="Cancel", command=edit_window.destroy,
                  width=10, relief="flat").pack(side=tk.LEFT, padx=8)

    def _refresh_row_display(self, index, row_data):
        children = self.tree.get_children()
        if index >= len(children):
            return
        item      = children[index]
        data_cols = self._get_active_data_cols()
        fixed_vals = [
            index + 1,
            row_data.get("Item NO.", ""),
            row_data.get("商品代码", ""),
            self.wrap_text(row_data.get("客户描述", ""), "客户描述"),
            row_data.get("数量", ""),
            row_data.get("UOM", ""),
        ]
        data_vals = [
            self.wrap_text(str(row_data.get(col, "")), col) for col in data_cols
        ]
        self.tree.item(item, values=fixed_vals + data_vals)
        self._apply_row_height_tag(item, index, row_data, data_cols)
        self.update_row_height()

    def copy_table_to_clipboard(self):
        if not self.query_results:
            messagebox.showwarning("警告", "没有数据可复制")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("导出报价表格")
        dialog.geometry("400x160")
        dialog.resizable(False, False)
        dialog.grab_set()

        tk.Label(dialog, text="选择导出方式：", font=('Helvetica', 12, 'bold')).pack(pady=(16, 8))

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=6)

        def do_html():
            dialog.destroy()
            self._copy_as_html()

        def do_eml():
            dialog.destroy()
            self._save_as_eml()

        def do_text():
            dialog.destroy()
            self._copy_as_text()

        tk.Button(btn_frame, text="复制表格\n在邮件粘贴即可",
                  command=do_html, width=18, height=2,
                  font=('Helvetica', 10), bg="#007aff", fg="white", relief="flat").pack(side=tk.LEFT, padx=6)

        tk.Button(btn_frame, text="导出邮件\n双击可用邮件客户端打开",
                  command=do_eml, width=20, height=2,
                  font=('Helvetica', 10), bg="#34c759", fg="white", relief="flat").pack(side=tk.LEFT, padx=6)

        tk.Button(btn_frame, text="复制纯文本",
                  command=do_text, width=10, height=2,
                  font=('Helvetica', 10), relief="flat").pack(side=tk.LEFT, padx=6)

    # ==================== 表格导出内部方法 ====================

    def _generate_html_table(self):
        """生成带框线的 HTML 表格字符串"""
        visible_columns = [col for col, var in self.column_visibility.items() if var.get()]

        th_style = (
            "border:1px solid #666; padding:6px 10px; "
            "background:#d0d7e3; font-weight:bold; "
            "font-family:Arial,sans-serif; font-size:13px; "
            "white-space:nowrap;"
        )
        td_style_even = (
            "border:1px solid #999; padding:5px 10px; "
            "font-family:Arial,sans-serif; font-size:12px; "
            "background:#ffffff;"
        )
        td_style_odd = (
            "border:1px solid #999; padding:5px 10px; "
            "font-family:Arial,sans-serif; font-size:12px; "
            "background:#f0f4fa;"
        )

        table_style = (
            "border-collapse:collapse; border:2px solid #555; "
            "font-family:Arial,sans-serif; font-size:12px;"
        )

        rows_html = ""
        for i, row_data in enumerate(self.query_results):
            td_s = td_style_even if i % 2 == 0 else td_style_odd
            cells = "".join(
                f'<td style="{td_s}">{str(row_data.get(col, "")).strip()}</td>'
                for col in visible_columns
            )
            rows_html += f"<tr>{cells}</tr>\n"

        header_cells = "".join(
            f'<th style="{th_style}">{col}</th>' for col in visible_columns
        )

        html = (
            f'<table style="{table_style}">'
            f"<thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
        )
        return html, visible_columns

    def _copy_as_html(self):
        """将 HTML 表格写入 Windows CF_HTML 剪贴板，可直接粘贴进 Outlook"""
        html_table, _ = self._generate_html_table()
        fragment = (
            "<html>\r\n<body>\r\n"
            "<!--StartFragment-->"
            + html_table
            + "<!--EndFragment-->\r\n</body>\r\n</html>"
        )

        try:
            import win32clipboard

            # 构建 CF_HTML 标准头部（偏移量需精确）
            header_tpl = (
                "Version:0.9\r\n"
                "StartHTML:{sh:08d}\r\n"
                "EndHTML:{eh:08d}\r\n"
                "StartFragment:{sf:08d}\r\n"
                "EndFragment:{ef:08d}\r\n"
            )
            # 先用占位头算出头部长度
            dummy = header_tpl.format(sh=0, eh=0, sf=0, ef=0)
            hdr_len = len(dummy.encode("utf-8"))

            body_bytes = fragment.encode("utf-8")
            sf = hdr_len + body_bytes.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
            ef = hdr_len + body_bytes.index(b"<!--EndFragment-->")
            sh = hdr_len
            eh = hdr_len + len(body_bytes)

            real_header = header_tpl.format(sh=sh, eh=eh, sf=sf, ef=ef)
            clip_data = (real_header + fragment).encode("utf-8")

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            cf_html = win32clipboard.RegisterClipboardFormat("HTML Format")
            win32clipboard.SetClipboardData(cf_html, clip_data)
            win32clipboard.CloseClipboard()

            messagebox.showinfo(
                "成功",
                "HTML 表格已复制到剪贴板\n\n"
                "请直接在 Outlook / 邮件正文中按 Ctrl+V 粘贴，\n"
                "表格框线会自动保留。"
            )

        except ImportError:
            messagebox.showwarning(
                "提示",
                "未找到 pywin32 模块，无法直接复制 HTML。\n\n"
                "请改用「另存为 .eml」方式，或运行：\n"
                "pip install pywin32"
            )
        except Exception as e:
            messagebox.showerror("错误", f"复制 HTML 失败：{str(e)}\n\n请改用「另存为 .eml」")

    def _save_as_eml(self):
        """生成标准 .eml 文件，双击可用 Outlook 等客户端直接打开"""
        import datetime
        from tkinter import filedialog
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        html_table, visible_columns = self._generate_html_table()

        full_html = (
            "<!DOCTYPE html>\r\n<html>\r\n"
            '<head><meta charset="utf-8"></head>\r\n'
            "<body>\r\n"
            "<p style=\"font-family:Arial,sans-serif;font-size:13px;\">"
            "报价结果如下，请查阅：</p>\r\n"
            + html_table
            + "\r\n</body>\r\n</html>"
        )

        # 纯文本备用（给不支持 HTML 的客户端）
        header_txt = " | ".join(visible_columns)
        sep_txt = "-" * len(header_txt)
        plain_lines = [header_txt, sep_txt]
        for row_data in self.query_results:
            plain_lines.append(
                " | ".join(str(row_data.get(col, "")).strip() for col in visible_columns)
            )
        plain_text = "\n".join(plain_lines)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"报价结果 {now_str}"
        msg["From"] = "quotation@company.com"
        msg["To"] = ""
        msg["Date"] = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800")

        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(full_html, "html", "utf-8"))

        default_name = f"报价结果_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.eml"
        filepath = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".eml",
            filetypes=[("邮件文件", "*.eml"), ("所有文件", "*.*")],
            initialfile=default_name,
            title="另存为邮件文件"
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(msg.as_string())
            messagebox.showinfo(
                "成功",
                f".eml 文件已保存：\n{filepath}\n\n"
                "双击该文件即可用 Outlook 等客户端打开，\n"
                "表格带完整框线，可直接转发或发送。"
            )
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _copy_as_text(self):
        """复制纯文本表格（原有行为）"""
        visible_columns = [col for col, var in self.column_visibility.items() if var.get()]
        header = " | ".join(visible_columns)
        separator = "-" * len(header)
        lines = [header, separator]
        for row_data in self.query_results:
            row = " | ".join(str(row_data.get(col, "")).strip() for col in visible_columns)
            lines.append(row)
        pyperclip.copy("\n".join(lines))
        messagebox.showinfo("成功", "纯文本表格已复制到剪贴板")

    def _toggle_lang(self):
        """切换 UI 语言（中文 ↔ 英文），同步刷新本窗口和价目表窗口的前端文字。"""
        new_lang = "en" if get_lang() == "zh" else "zh"
        set_lang(new_lang)
        self._lang_btn.config(text="中文" if new_lang == "en" else "EN")
        # 刷新本窗口
        self._refresh_ui_lang()
        # 同步刷新价目表窗口（若已创建）
        try:
            from main import main_app_instance
            if main_app_instance is not None and main_app_instance.winfo_exists():
                main_app_instance.refresh_lang()
        except Exception:
            pass

    def _refresh_ui_lang(self):
        """把所有存储的 widget 文字刷新为当前语言。"""
        # ── 静态标签 & 按钮 ──────────────────────────────────────────────────
        label_map = {
            'lbl_company': "公司代码",
            'lbl_itemcode': "商品代码",
            'lbl_showcols': "显示列:",
        }
        for key, zh_text in label_map.items():
            w = self._lang_widgets.get(key)
            if w:
                w.config(text=t(zh_text))

        btn_map = {
            'btn_ocr': "OCR识别",
            'btn_append': "追加识别",
            'btn_query': "查询价格",
            'btn_copy': "复制表格",
            'btn_clear': "清空",
        }
        for key, zh_text in btn_map.items():
            w = self._lang_widgets.get(key)
            if w:
                w.config(text=t(zh_text))

        # ── 列显示复选框 ──────────────────────────────────────────────────────
        for col_name, cb in self._col_checkbuttons.items():
            try:
                cb.config(text=t(col_name))
            except Exception:
                pass

        # ── Treeview 固定列表头 ───────────────────────────────────────────────
        fixed_zh = {"行号": "行号", "客户描述": "客户描述", "数量": "数量"}
        for col_id, zh_text in fixed_zh.items():
            try:
                self.tree.heading(col_id, text=t(zh_text))
            except Exception:
                pass

        # ── Treeview 数据列表头（FL_DISPLAY 动态列）─────────────────────────
        try:
            for col_id in self.tree["columns"]:
                if col_id in fixed_zh:
                    continue
                try:
                    self.tree.heading(col_id, text=t(col_id))
                except Exception:
                    pass
        except Exception:
            pass

        # ── codes_label：只刷新默认提示文字，有内容时不覆盖 ─────────────────
        current = self.codes_label.cget("text")
        if current in ("未识别到商品代码", "No item code recognized"):
            self.codes_label.config(text=t("未识别到商品代码"))

    def clear_all(self):
        self.product_items = []
        self.query_results = []
        self.company_var.set("")
        self.pricing_type = None
        self.selected_tree_item = None
        self.codes_label.config(text="未识别到商品代码")
        self.query_button.config(state=tk.DISABLED)
        self.hide_suggestions()

        for item in self.tree.get_children():
            self.tree.delete(item)

        style = ttk.Style()
        style.configure('Custom.Treeview', rowheight=self.unit_height)

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()