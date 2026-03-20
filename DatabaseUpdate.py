"""
DatabaseUpdate.py
从 Excel 文件读取数据并写入（或更新） database_data.db 中对应的表。
- Excel 第一行作为列名
- 表名取自 Excel 文件名（去掉扩展名），空格替换为下划线
- 若表已存在则先删除再重建（全量替换）
- 支持 .xlsx / .xls / .xlsm
"""

import os
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

from config import get_db_path

# 动态路径，打包和开发环境均正确
# 注意：不在模块加载时固化路径，而是调用时解析，确保打包环境路径正确
DB_PATH = get_db_path()
# ───────────────────────────────────────────────
# 核心：读取 Excel → 写入 SQLite
# ───────────────────────────────────────────────

def _read_excel(filepath: str):
    """
    读取 Excel，返回 (table_name, columns, rows)
    columns : list[str]   第一行表头
    rows    : list[tuple] 数据行
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active

        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if not all_rows:
            raise ValueError("Excel 文件为空，无法读取数据")

        # 第一行作为列名，None 列名替换为 col_N
        raw_headers = all_rows[0]
        columns = []
        for i, h in enumerate(raw_headers):
            name = str(h).strip() if h is not None else f"col_{i}"
            # SQLite 列名不能含特殊字符，替换掉常见问题字符
            name = name.replace(" ", "_").replace("/", "_").replace("-", "_")
            name = name.replace("(", "").replace(")", "").replace(".", "_")
            columns.append(name)

        # 数据行：空行跳过
        rows = []
        for raw in all_rows[1:]:
            if any(cell is not None and str(cell).strip() != "" for cell in raw):
                # 补齐长度
                row = list(raw) + [None] * (len(columns) - len(raw))
                rows.append(tuple(row[:len(columns)]))

        # 表名固定为 FullList，与 Excel 文件名无关
        table_name = "FullList"

        return table_name, columns, rows

    except ImportError:
        raise ImportError("缺少 openpyxl 库，请运行：pip install openpyxl")


def import_excel_to_db(filepath: str, db_path: str = None,
                       progress_callback=None, status_callback=None):
    """
    将 Excel 数据导入 SQLite。
    progress_callback(value: int)  : 0-100 进度
    status_callback(msg: str)      : 状态文字
    返回 (table_name, row_count)
    """
    db_path = db_path or get_db_path()  # None 时运行时解析，避免打包路径固化
    def _status(msg):
        if status_callback:
            status_callback(msg)

    def _progress(v):
        if progress_callback:
            progress_callback(v)

    _status("正在读取 Excel 文件...")
    _progress(5)
    table_name, columns, rows = _read_excel(filepath)

    _status(f"识别到表名：{table_name}，共 {len(columns)} 列，{len(rows)} 行数据")
    _progress(20)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 删除旧表（全量替换）
        cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')

        # 建表：所有列均为 TEXT，避免类型推断错误
        col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
        cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
        _progress(35)

        # 批量插入
        placeholders = ", ".join("?" * len(columns))
        col_names = ", ".join(f'"{c}"' for c in columns)
        insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'

        batch_size = 500
        total = len(rows)
        for i in range(0, total, batch_size):
            batch = rows[i: i + batch_size]
            # 将所有值转为字符串（None 保持 None）
            clean_batch = [
                tuple(str(v).strip() if v is not None else None for v in row)
                for row in batch
            ]
            cursor.executemany(insert_sql, clean_batch)
            pct = 35 + int((i + len(batch)) / total * 60)
            _progress(min(pct, 95))
            _status(f"正在写入数据... {min(i + batch_size, total)}/{total} 行")

        conn.commit()
        _progress(100)
        _status(f"完成！表 [{table_name}] 已写入 {total} 行数据。")
        return table_name, total

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ───────────────────────────────────────────────
# GUI 弹窗
# ───────────────────────────────────────────────

class DatabaseUpdateWindow:
    """
    独立的数据库更新弹窗。
    parent: 父窗口（tkinter widget），可为 None。
    """

    def __init__(self, parent=None):
        self.parent = parent
        self.win = tk.Toplevel(parent) if parent else tk.Tk()
        if not parent:
            self.win.title("更新价目表数据库")
            self.win.geometry("560x340")
            self.win.resizable(False, False)
        if parent:
            self.win.transient(parent)
            self.win.grab_set()

        self._build_ui()

    def _build_ui(self):
        win = self.win
        pad = dict(padx=16, pady=6)

        # ── 文件选择区 ──
        file_frame = tk.LabelFrame(win, text="选择 Excel 文件", font=("Helvetica", 11, "bold"),
                                   padx=10, pady=8)
        file_frame.pack(fill="x", padx=16, pady=(14, 6))

        self.file_var = tk.StringVar(value="（尚未选择文件）")
        tk.Label(file_frame, textvariable=self.file_var, anchor="w",
                 fg="#333333", font=("Helvetica", 10),
                 wraplength=460, justify="left").pack(side="left", fill="x", expand=True)

        tk.Button(file_frame, text="浏览...", command=self._browse,
                  font=("Helvetica", 10), bg="#007aff", fg="white",
                  relief="flat", padx=10).pack(side="right")

        # ── 数据库路径 ──
        db_frame = tk.Frame(win)
        db_frame.pack(fill="x", padx=16, pady=4)
        tk.Label(db_frame, text="目标数据库：", font=("Helvetica", 10)).pack(side="left")
        self.db_var = tk.StringVar(value=os.path.abspath(get_db_path()))
        tk.Label(db_frame, textvariable=self.db_var, fg="#555555",
                 font=("Helvetica", 10), anchor="w").pack(side="left", fill="x", expand=True)

        # ── 进度条 ──
        prog_frame = tk.Frame(win)
        prog_frame.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(prog_frame, text="进度：", font=("Helvetica", 10)).pack(side="left")
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var,
                                            maximum=100, length=420)
        self.progress_bar.pack(side="left", fill="x", expand=True)

        # ── 状态文字 ──
        self.status_var = tk.StringVar(value="请先选择 Excel 文件")
        tk.Label(win, textvariable=self.status_var, anchor="w", fg="#444444",
                 font=("Helvetica", 10), wraplength=520, justify="left").pack(
            fill="x", padx=16, pady=(2, 8))

        # ── 按钮区 ──
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=(4, 14))

        self.import_btn = tk.Button(btn_frame, text="开始导入",
                                    command=self._start_import,
                                    font=("Helvetica", 11, "bold"),
                                    bg="#34c759", fg="white",
                                    relief="flat", padx=20, pady=6,
                                    state="disabled")
        self.import_btn.pack(side="left", padx=10)

        tk.Button(btn_frame, text="关闭", command=self.win.destroy,
                  font=("Helvetica", 11), relief="flat",
                  padx=20, pady=6).pack(side="left", padx=10)

        self._filepath = None

    def _browse(self):
        path = filedialog.askopenfilename(
            parent=self.win,
            title="选择 Excel 文件",
            filetypes=[
                ("Excel 文件", "*.xlsx *.xls *.xlsm"),
                ("所有文件", "*.*")
            ]
        )
        if path:
            self._filepath = path
            self.file_var.set(path)
            self.status_var.set("文件已选择，点击「开始导入」写入数据库")
            self.import_btn.config(state="normal")
            self.progress_var.set(0)

    def _start_import(self):
        if not self._filepath:
            messagebox.showwarning("提示", "请先选择 Excel 文件", parent=self.win)
            return

        self.import_btn.config(state="disabled")
        self.progress_var.set(0)

        def _run():
            try:
                table_name, row_count = import_excel_to_db(
                    self._filepath,
                    db_path=self.db_var.get(),
                    progress_callback=lambda v: self.win.after(0, self.progress_var.set, v),
                    status_callback=lambda m: self.win.after(0, self.status_var.set, m)
                )
                self.win.after(0, lambda: messagebox.showinfo(
                    "导入成功",
                    f"表 [{table_name}] 已成功写入数据库\n共导入 {row_count} 行数据",
                    parent=self.win
                ))
            except Exception as e:
                self.win.after(0, lambda err=e: messagebox.showerror(
                    "导入失败", f"错误信息：{str(err)}", parent=self.win
                ))
                self.win.after(0, self.status_var.set, f"导入失败：{e}")
            finally:
                self.win.after(0, lambda: self.import_btn.config(state="normal"))

        threading.Thread(target=_run, daemon=True).start()


# ───────────────────────────────────────────────
# 对外调用入口（供其他模块 import）
# ───────────────────────────────────────────────

def open_update_window(parent=None):
    """在 parent 窗口上弹出数据库更新窗口"""
    DatabaseUpdateWindow(parent)


# ───────────────────────────────────────────────
# 独立运行入口
# ───────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.title("更新价目表数据库")
    root.geometry("560x340")
    root.resizable(False, False)

    # 直接在 root 上构建 UI，不用 Toplevel，避免主循环未启动时子线程调用 after() 报错
    app = DatabaseUpdateWindow.__new__(DatabaseUpdateWindow)
    app.parent = None
    app.win = root
    app._filepath = None
    app._build_ui()

    root.mainloop()