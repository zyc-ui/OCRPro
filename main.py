import tkinter as tk
from tkinter import ttk
import sqlite3
from typing import List, Tuple, Dict, Set, Any

import sys
import os
import traceback
import logging

from PIL import ImageTk, Image
from config import (
    get_db_path, FL_DISPLAY, FL_DB_COLS, FL_COL_WIDTHS,
    FL_COMPANY_DISPLAY_TO_IDX, PRICE_COL_START_IDX,
)

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)


def get_base_path():
    """获取基础路径：打包环境使用_MEIPASS，开发环境使用当前目录"""
    try:
        base_path = sys._MEIPASS
        logging.info("运行在打包环境")
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
        logging.info("运行在开发环境")
    return base_path


def get_resource_path(relative_path):
    """获取资源文件的绝对路径"""
    base_path = get_base_path()
    path = os.path.join(base_path, relative_path)
    logging.debug(f"资源路径: {relative_path} -> {path}")
    return path


# -------------------- 自定义圆角按钮类 --------------------
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, width=80, height=30, corner_radius=8,
                 bg="#e9ecef", fg="#212529", hover_bg="#dee2e6", active_bg="#ced4da",
                 selected_bg="#0d6efd", selected_fg="#ffffff", font=("SF Pro Display", 13, "bold"),
                 *args, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0,
                         bg=parent["bg"], *args, **kwargs)

        self.command = command
        self.text = text
        self.corner_radius = corner_radius
        self.bg = bg
        self.fg = fg
        self.hover_bg = hover_bg
        self.active_bg = active_bg
        self.selected_bg = selected_bg
        self.selected_fg = selected_fg
        self.font = font
        self.current_bg = bg
        self.current_fg = fg
        self.is_selected = False

        # 绑定事件
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<ButtonPress-1>", self.on_press)  # 按下：视觉反馈
        self.bind("<ButtonRelease-1>", self.on_release)  # 松手：恢复视觉
        self.bind("<ButtonRelease-1>", self.on_click, add='+')  # 松手：触发命令（Entry内容已稳定）
        self.bind("<Configure>", lambda e: self.draw_button())

        self.draw_button()

    def draw_button(self):
        """绘制圆角按钮（背景+文字）"""
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()

        # 绘制圆角矩形背景
        self.create_rounded_rectangle(0, 0, w, h, radius=self.corner_radius,
                                      fill=self.current_bg, outline="")

        # 绘制居中文字
        self.create_text(w // 2, h // 2, text=self.text, fill=self.current_fg, font=self.font)

    def create_rounded_rectangle(self, x1, y1, x2, y2, radius=25, **kwargs):
        """绘制圆角矩形的核心方法"""
        points = [
            x1 + radius, y1,  # 左上角圆弧起点
            x2 - radius, y1,  # 右上角圆弧起点
            x2, y1, x2, y1 + radius,  # 右上角圆弧
            x2, y2 - radius,  # 右下角圆弧起点
            x2, y2, x2 - radius, y2,  # 右下角圆弧
            x1 + radius, y2,  # 左下角圆弧起点
            x1, y2, x1, y2 - radius,  # 左下角圆弧
            x1, y1 + radius,  # 左上角圆弧起点
            x1, y1, x1 + radius, y1  # 左上角圆弧
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def on_enter(self, event):
        """鼠标悬浮时的样式变化"""
        if not self.is_selected:
            self.current_bg = self.hover_bg
            self.draw_button()

    def on_leave(self, event):
        """鼠标离开时的样式恢复"""
        if not self.is_selected:
            self.current_bg = self.bg
            self.draw_button()

    def on_press(self, event):
        """鼠标按下时的样式变化"""
        if not self.is_selected:
            self.current_bg = self.active_bg
            self.draw_button()

    def on_release(self, event):
        """鼠标释放时的样式恢复"""
        if not self.is_selected:
            self.current_bg = self.hover_bg
            self.draw_button()

    def on_click(self, event):
        """按钮点击事件"""
        if self.command:
            try:
                self.command()
            except Exception as e:
                import logging
                logging.error(f"按钮命令执行出错: {e}", exc_info=True)

    def set_selected(self, selected=True):
        """设置按钮选中状态"""
        self.is_selected = selected
        if selected:
            self.current_bg = self.selected_bg
            self.current_fg = self.selected_fg
        else:
            self.current_bg = self.bg
            self.current_fg = self.fg
        self.draw_button()

    def update_text(self, new_text):
        """更新按钮文字"""
        self.text = new_text
        self.draw_button()


# -------------------- 延迟导入 --------------------
def import_translate():
    """延迟导入translate模块"""
    try:
        from translate import t, set_lang
        return t, set_lang
    except ImportError as e:
        logging.error(f"导入translate失败: {e}")

        def dummy_t(key):
            return key

        def dummy_set_lang(lang):
            pass

        return dummy_t, dummy_set_lang


def import_window_module(module_name, class_name):
    """动态导入窗口模块"""
    try:
        module = __import__(module_name)
        window_class = getattr(module, class_name)
        return window_class
    except (ImportError, AttributeError) as e:
        logging.error(f"导入{module_name}.{class_name}失败: {e}")

        class DummyWindow:
            def __init__(self, parent=None):
                logging.error(f"{class_name}不可用")

        return DummyWindow

# -------------------- 数据库配置 --------------------
DB_CFG = {
    'database': 'database_data.db'
}


# -------------------- 数据访问 --------------------
def fetch_fulllist_for_price_view(company_name: str):
    """
    从 FullList 读取全量数据，返回 (price_cols, data)。
    price_cols : 实际显示的列名列表（FL_DISPLAY 子集）
    data       : list of tuples，每行按 price_cols 顺序排列
    """
    company_col_idx = _determine_company_col_idx(company_name)
    if company_col_idx is not None:
        price_display_cols = [FL_DISPLAY[company_col_idx]]
        price_db_cols      = [FL_DB_COLS[company_col_idx]]
    else:
        price_display_cols = [FL_DISPLAY[23], FL_DISPLAY[24]]   # High + Medium
        price_db_cols      = [FL_DB_COLS[23],  FL_DB_COLS[24]]

    # 信息列：索引 0 到 PRICE_COL_START_IDX-1（即 0-21）
    base_display = FL_DISPLAY[:PRICE_COL_START_IDX]
    base_db      = FL_DB_COLS[:PRICE_COL_START_IDX]

    all_display = base_display + price_display_cols
    all_db      = base_db      + price_db_cols

    select_cols = ", ".join(f'"{c}"' for c in all_db)
    sql = f'SELECT {select_cols} FROM "FullList" ORDER BY "NO_"'

    try:
        conn   = sqlite3.connect(get_db_path())   # ← get_db_path() from config
        cursor = conn.cursor()
        cursor.execute(sql)
        rows   = cursor.fetchall()
        conn.close()
        return all_display, rows
    except Exception as e:
        logging.error(f"FullList 查询失败: {e}")
        return all_display, []


def _determine_company_col_idx(company_name: str):
    """返回公司显示名对应 FL_DISPLAY 的索引（26-33），无匹配返回 None"""
    if not company_name or company_name.strip().lower() in ("", "other"):
        return None
    return FL_COMPANY_DISPLAY_TO_IDX.get(company_name.strip())


def get_all_table_names() -> List[str]:
    """获取数据库中所有用户表名"""
    try:
        conn = sqlite3.connect(get_db_path())   # ← get_db_path() from config
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        logging.debug(f"获取到表名: {tables}")
        return tables
    except Exception as e:
        logging.error(f"获取表名失败: {e}")
        return []

def get_table_columns(table_name: str) -> List[str]:
    """获取指定表的所有列名"""
    try:
        conn = sqlite3.connect(get_db_path())   # ← get_db_path() from config
        cursor = conn.cursor()
        cursor.execute(f'PRAGMA table_info("{table_name}")')   # ← 表名加引号防注入
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        logging.debug(f"表 {table_name} 的列: {columns}")
        return columns
    except Exception as e:
        logging.error(f"获取表 {table_name} 列信息失败: {e}")
        return []


def search_all_tables(keyword: str) -> Dict[str, Tuple[List[str], List[Tuple]]]:
    """
    在所有表中搜索关键词
    返回: {表名: (列名列表, 数据行列表)}
    """
    results = {}
    tables = get_all_table_names()

    if not tables:
        return results

    for table in tables:
        try:
            # 获取表的列信息
            columns = get_table_columns(table)
            if not columns:
                continue

            # 构建搜索条件（在所有文本列中搜索）
            conditions = []
            params = []

            for col in columns:
                conditions.append(f"{col} LIKE ?")
                params.append(f"%{keyword}%")

            where_clause = " OR ".join(conditions)
            sql = f"SELECT * FROM {table} WHERE {where_clause}"

            conn = sqlite3.connect(DB_CFG['database'])
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            conn.close()

            if rows:  # 只返回有结果的表
                results[table] = (columns, rows)
                logging.debug(f"在表 {table} 中找到 {len(rows)} 条结果")

        except Exception as e:
            logging.error(f"搜索表 {table} 时出错: {e}")

    return results


def get_table_data(table_name: str, limit: int = 1000) -> Tuple[List[str], List[Tuple]]:
    """
    获取指定表的所有数据（限制最大行数）
    返回: (列名列表, 数据行列表)
    """
    try:
        columns = get_table_columns(table_name)
        if not columns:
            return [], []

        sql = f'SELECT * FROM "{table_name}" LIMIT {limit}'   # ← 表名加引号

        conn = sqlite3.connect(get_db_path())   # ← get_db_path() from config
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()

        return columns, rows
    except Exception as e:
        logging.error(f"获取表 {table_name} 数据时出错: {e}")
        return [], []

def search_all_tables_with_limit(
    keyword: str,
    limit_per_table: int = 1000,
) -> Dict[str, Tuple[List[str], List[Tuple]]]:
    """
    在所有用户表中搜索关键词，限制每个表的最大结果数。

    修复：
    - 原代码每张表各开关一次 SQLite 连接，改为单连接遍历所有表
    - 路径改用 get_db_path()，打包环境也能正确找到数据库
    - 列名和表名均加引号，防止特殊字符导致 SQL 错误
    """
    results: Dict[str, Tuple[List[str], List[Tuple]]] = {}

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
    except Exception as e:
        logging.error(f"[DB] 无法连接数据库: {e}")
        return results

    try:
        # 1. 单次查询获取所有用户表名
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables: List[str] = [row[0] for row in cursor.fetchall()]

        for table in tables:
            try:
                # 2. 获取列信息
                cursor.execute(f'PRAGMA table_info("{table}")')
                columns: List[str] = [row[1] for row in cursor.fetchall()]
                if not columns:
                    continue

                # 3. 构建 WHERE 子句（列名加引号防止特殊字符出错）
                conditions = " OR ".join(f'"{c}" LIKE ?' for c in columns)
                params = [f"%{keyword}%"] * len(columns)

                cursor.execute(
                    f'SELECT * FROM "{table}" WHERE {conditions} LIMIT {limit_per_table}',
                    params,
                )
                rows = cursor.fetchall()
                if rows:
                    results[table] = (columns, rows)
                    logging.debug(f"[Search] 表 {table}: {len(rows)} 条匹配")

            except Exception as e:
                logging.error(f"[Search] 搜索表 {table} 出错: {e}")
                # 不中断其他表的搜索，继续下一张表

    finally:
        conn.close()   # 无论如何关闭连接，防止资源泄漏

    return results

def get_table_display_name(table_name: str) -> str:
    """获取表的显示名称（可自定义映射）"""
    # 这里可以添加自定义的表名映射
    display_names = {
        "seastar_full_list_ind_co": "seastar full list ind co",
        "fluke_2025": "fluke 2025",
        "haixing": "Hai Xing",
    }
    return display_names.get(table_name, table_name)


# ==================== 全局搜索高亮系统（仅高亮匹配项） ====================
class GlobalSearchHighlighter:
    """
    全局搜索结果的高亮与定位系统
    仅高亮匹配项，其余内容保持正常显示
    """

    def __init__(self, app_instance):
        """初始化高亮系统"""
        self.app = app_instance  # SeaStarApp 实例引用

        # 每个标签页独立的匹配状态
        self.tab_matches = {}  # {tab_name: {"items": [], "index": 0, "tree": None}}
        self.current_tab_name = None  # 当前激活的标签页

        # 高亮样式配置（仅匹配项高亮，其余保持默认）
        self.highlight_style = {
            'matched': {'background': '#0d6efd', 'foreground': '#ffffff',
                        'font': self.app.tree_content_font},
            # normal样式完全继承Treeview默认样式
            'normal': {'background': '', 'foreground': '', 'font': ''}
        }

        # 绑定标签页切换事件
        self.app.global_notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def setup_tree_tags(self, tree):
        """为Treeview设置高亮标签样式（仅配置匹配项，normal不做额外配置）"""
        # 仅配置匹配项的高亮样式
        tree.tag_configure('matched',
                           background=self.highlight_style['matched']['background'],
                           foreground=self.highlight_style['matched']['foreground'],
                           font=self.highlight_style['matched']['font'])
        # normal标签不配置样式，继承Treeview默认
        tree.tag_configure('normal')

    def on_tab_changed(self, event):
        """标签页切换时更新当前匹配状态"""
        # 获取当前选中的标签页ID
        current_tab_id = self.app.global_notebook.select()
        if not current_tab_id:
            return

        # 查找对应的标签页名称
        for tab_name, (frame, tree) in self.app.global_tabs.items():
            tab_id = self.app.global_notebook.tabs()[list(self.app.global_tabs.keys()).index(tab_name)]
            if tab_id == current_tab_id:
                self.current_tab_name = tab_name
                # 如果当前标签页有匹配项，自动定位到第一个
                if tab_name in self.tab_matches and self.tab_matches[tab_name]["items"]:
                    self.goto_first_match()
                break

    def perform_highlighted_search(self, keyword):
        """
        执行带高亮的全局搜索
        - 仅高亮匹配项，其余内容保持正常显示
        - 定位到第一个匹配项
        - 支持F3/Shift+F3导航
        """
        keyword = keyword.strip().upper()
        if not keyword:
            self.clear_all_highlights()
            self.app.result_stats_label.config(text="请输入搜索关键词")
            return

        self.app.global_search_title.config(text=f"全局搜索: {keyword}")
        self.app.result_stats_label.config(text="搜索并高亮匹配项中...")
        self.app.update()

        # 清空所有现有高亮和匹配状态
        self.clear_all_highlights()
        self.tab_matches = {}

        # 搜索结果统计
        total_matches = 0
        tabs_with_matches = []
        tab_match_details = {}

        # 为每个标签页的Treeview搜索并仅高亮匹配项
        for tab_name, (frame, tree) in self.app.global_tabs.items():
            # 仅高亮匹配项，其余保持正常
            matched_items = self.highlight_in_tree(tree, keyword)
            tab_match_count = len(matched_items)

            if matched_items:
                total_matches += tab_match_count
                tabs_with_matches.append(tab_name)
                tab_match_details[tab_name] = tab_match_count

                # 保存当前标签页的匹配状态
                self.tab_matches[tab_name] = {
                    "items": matched_items,
                    "index": 0,
                    "tree": tree
                }

                # 更新标签页标题（显示匹配数量）
                self.update_tab_title(tab_name, tab_match_count)

                # 默认选中第一个有匹配项的标签页
                if self.current_tab_name is None:
                    self.current_tab_name = tab_name
                    # 切换到该标签页
                    tab_index = list(self.app.global_tabs.keys()).index(tab_name)
                    self.app.global_notebook.select(tab_index)

        # 显示详细的匹配统计
        if total_matches == 0:
            stats_text = f"未找到包含 '{keyword}' 的匹配项"
        else:
            stats_text = f"共找到 {total_matches} 处匹配 | 分布在 {len(tabs_with_matches)} 个表中 | F3=下一个 | Shift+F3=上一个"
            # 显示各表匹配详情
            detail_text = " | ".join(
                [f"{get_table_display_name(tab)}:{cnt}条" for tab, cnt in tab_match_details.items()])
            stats_text += f"\n匹配详情: {detail_text}"

            # 定位到第一个匹配项
            self.goto_first_match()
            # 绑定导航快捷键
            self.bind_navigation_keys()

        self.app.result_stats_label.config(text=stats_text)

    def highlight_in_tree(self, tree, keyword):
        """
        在单个Treeview中仅高亮匹配关键词的行
        - 匹配项：应用高亮样式
        - 非匹配项：移除所有标签，恢复默认显示
        - 返回匹配项ID列表
        """
        # 获取所有项
        all_items = tree.get_children()
        matched_items = []

        # 遍历所有项，仅高亮匹配项
        for item in all_items:
            values = tree.item(item, "values")
            is_matched = False

            # 检查每个单元格是否包含关键词（不区分大小写）
            for cell in values:
                cell_str = str(cell).strip().upper()
                if keyword in cell_str:
                    is_matched = True
                    break

            if is_matched:
                # 匹配项：应用高亮样式
                tree.item(item, tags=('matched',))
                matched_items.append(item)
            else:
                # 非匹配项：移除标签，恢复默认显示
                tree.item(item, tags=('normal',))

        return matched_items

    def clear_all_highlights(self):
        """清除所有Treeview中的高亮，恢复默认显示"""
        for tab_name, (frame, tree) in self.app.global_tabs.items():
            # 清除所有项的标签，恢复默认显示
            for item in tree.get_children():
                tree.item(item, tags=('normal',))
            # 恢复原始标签页标题
            self.reset_tab_title(tab_name)

        # 重置匹配状态
        self.tab_matches = {}
        self.current_tab_name = None

        # 解绑导航快捷键
        self.unbind_navigation_keys()

    def update_tab_title(self, tab_name, match_count):
        """更新标签页标题（显示匹配数量）"""
        if match_count > 0:
            display_name = get_table_display_name(tab_name)
            # 移除已有的匹配数量，避免重复显示
            for i, tab_id in enumerate(self.app.global_notebook.tabs()):
                tab_text = self.app.global_notebook.tab(tab_id, "text")
                base_text = tab_text.split(" (")[0] if " (" in tab_text else tab_text
                if base_text == display_name:
                    self.app.global_notebook.tab(tab_id, text=f"{display_name} ({match_count}条匹配)")
                    break

    def reset_tab_title(self, tab_name):
        """重置标签页标题为原始名称"""
        display_name = get_table_display_name(tab_name)
        for i, tab_id in enumerate(self.app.global_notebook.tabs()):
            tab_text = self.app.global_notebook.tab(tab_id, "text")
            if tab_text.startswith(display_name):
                base_text = tab_text.split(" (")[0]
                self.app.global_notebook.tab(tab_id, text=base_text)
                break

    def goto_first_match(self):
        """定位到第一个匹配项"""
        if not self.current_tab_name or self.current_tab_name not in self.tab_matches:
            return

        tab_match = self.tab_matches[self.current_tab_name]
        if not tab_match["items"]:
            return

        # 重置索引
        tab_match["index"] = 0
        first_match = tab_match["items"][0]
        tree = tab_match["tree"]

        # 选择并滚动到该项
        tree.selection_set(first_match)
        tree.see(first_match)

        # 精确滚动到顶部附近
        index = tree.get_children().index(first_match)
        tree.yview_moveto(max(0, (index - 2) / len(tree.get_children())))

    def goto_next_match(self, event=None):
        """导航到下一个匹配项"""
        if not self.current_tab_name or self.current_tab_name not in self.tab_matches:
            return

        tab_match = self.tab_matches[self.current_tab_name]
        matched_items = tab_match["items"]

        if len(matched_items) <= 1:
            return  # 只有一个匹配项时不导航

        # 循环索引
        tab_match["index"] = (tab_match["index"] + 1) % len(matched_items)
        next_match = matched_items[tab_match["index"]]
        tree = tab_match["tree"]

        # 选择并滚动到下一个匹配项
        tree.selection_set(next_match)
        tree.see(next_match)

        # 精确滚动到顶部附近
        index = tree.get_children().index(next_match)
        tree.yview_moveto(max(0, (index - 2) / len(tree.get_children())))

        # 显示当前匹配位置
        current_idx = tab_match["index"] + 1
        total = len(matched_items)
        self.app.result_stats_label.config(
            text=self.app.result_stats_label.cget("text").split(" | ")[0] +
                 f" | 当前: {current_idx}/{total} (按F3继续)"
        )

    def goto_prev_match(self, event=None):
        """导航到上一个匹配项"""
        if not self.current_tab_name or self.current_tab_name not in self.tab_matches:
            return

        tab_match = self.tab_matches[self.current_tab_name]
        matched_items = tab_match["items"]

        if len(matched_items) <= 1:
            return

        # 循环索引
        tab_match["index"] = (tab_match["index"] - 1) % len(matched_items)
        prev_match = matched_items[tab_match["index"]]
        tree = tab_match["tree"]

        # 选择并滚动到上一个匹配项
        tree.selection_set(prev_match)
        tree.see(prev_match)

        # 精确滚动到顶部附近
        index = tree.get_children().index(prev_match)
        tree.yview_moveto(max(0, (index - 2) / len(tree.get_children())))

        # 显示当前匹配位置
        current_idx = tab_match["index"] + 1
        total = len(matched_items)
        self.app.result_stats_label.config(
            text=self.app.result_stats_label.cget("text").split(" | ")[0] +
                 f" | 当前: {current_idx}/{total} (按Shift+F3继续)"
        )

    def bind_navigation_keys(self):
        """绑定导航快捷键"""
        self.app.bind('<F3>', self.goto_next_match)
        self.app.bind('<Shift-F3>', self.goto_prev_match)

    def unbind_navigation_keys(self):
        """解绑导航快捷键"""
        self.app.unbind('<F3>')
        self.app.unbind('<Shift-F3>')


# ==================== UI 实现 ====================
class SeaStarApp(tk.Tk):
    def hide_window(self):
        """隐藏窗口（用于双击选择后）"""
        self.withdraw()  # 隐藏窗口

    def show_window(self):
        """显示窗口"""
        self.deiconify()  # 显示窗口
        self.state('zoomed')  # 最大化
        self.lift()  # 置顶
        self.focus_force()  # 强制获取焦点

    def show_price_list_from_external(self, company_name, search_keyword=None,
                                       pricing_type=None, keyword_list=None,
                                       customer_code=None, customer_desc=None):
        """从外部系统（价格查询工具）显示价目表"""
        self.show_window()

        # 捕获当前搜索栏内容（show_price_list 会清空）
        pre_existing_search = self.search_var.get().strip()

        if pricing_type is None:
            pricing_type = self._get_pricing_type_from_name(company_name)

        # 存储定位关键词供定位按钮使用
        self._last_locate_keyword = search_keyword

        # 更新客户商品信息标签
        # 更新客户商品信息标签（每次强制刷新，避免残留）
        self._customer_info_label.pack_forget()  # ← 先统一隐藏
        if customer_code or customer_desc:
            parts = []
            if customer_code:
                parts.append(f"IMPA：{customer_code}")
            if customer_desc:
                parts.append(f"Descrition：{customer_desc}")
            self._customer_info_label.config(text="    |    ".join(parts))
            self._customer_info_label.pack(
                fill="x", pady=(0, 5),
                before=self._row_lines_label.master
            )
        else:
            self._customer_info_label.config(text="")  # ← 同时清空文本

        self.show_price_list(company_name, pricing_type)

        self.lift()
        self.focus_force()
        self.update()

        # 更新关键词选择器
        if keyword_list:
            self.after(120, lambda kl=keyword_list: self.update_keyword_picker(kl))

        if pre_existing_search:
            # 搜索栏原来有内容：恢复后搜索，定位关键词在后台待命
            self.search_var.set(pre_existing_search)
            self._pending_search_keyword = search_keyword
            self.after(350, self.search_price_list)
        elif search_keyword and getattr(self, '_locate_active', True):
            # 搜索栏为空 + 定位激活：300ms 后安全执行蓝色高亮定位
            self.after(300, lambda kw=search_keyword: self._safe_initial_locate(kw))

        return self

    def set_initial_search(self, keyword):
        """设置初始搜索关键词"""
        if keyword and hasattr(self, 'price_tree') and self.price_tree.winfo_exists():
            # 清空搜索框
            self.search_var.set("")
            # 设置初始搜索关键词
            self.initial_search_keyword = keyword
            self.blue_highlight_keyword = keyword
            # 执行初始搜索
            self.perform_initial_search(keyword)
            # 将焦点设置到搜索框
            self.search_entry.focus_set()
            self.search_entry.icursor(0)

    def _get_pricing_type_from_name(self, company_name):
        """兼容旧调用，实际不再使用 H/M/L，返回空字符串"""
        return ""

    def __init__(self):
        super().__init__()
        self.current_view = 'price'  # 默认显示价目表界面

        # 初始搜索关键词
        self.initial_search_keyword = None
        self.initial_highlight_items = []

        # 添加搜索事件跟踪ID存储
        self._search_trace_id = None
        # 延迟导入翻译函数
        self.t, self.set_lang = import_translate()

        # 获取屏幕尺寸
        self.screen_width = self.winfo_screenwidth()
        self.screen_height = self.winfo_screenheight()

        self.set_lang("zh")
        self.title("UMIHOSHI  v0.0.1")

        # 添加新的属性来跟踪蓝色高亮
        self.blue_highlight_items = []
        self.blue_highlight_keyword = ""

        # 添加双击选择回调函数存储
        self.price_tree_select_callback = None

        # 默认窗口大小（调整为更大以适应价目表）
        default_width = int(self.screen_width * 0.9)
        default_height = int(self.screen_height * 0.9)
        self.geometry(f"{default_width}x{default_height}")
        self.update_idletasks()
        x = (self.screen_width - default_width) // 2
        y = (self.screen_height - default_height) // 2
        self.geometry(f"+{x}+{y}")

        # 设置窗口关闭行为为隐藏而不是销毁
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # ========== 白底黑字配色体系（全局统一） ==========
        self.bg_primary = "#ffffff"  # 主背景（纯白）
        self.bg_surface = "#f8f9fa"  # 磨砂表面底色（浅灰）
        self.bg_frosted = "#e9ecef"  # 按钮默认色（淡灰）
        self.bg_frosted_hover = "#dee2e6"  # 按钮hover色（浅灰）
        self.bg_frosted_active = "#ced4da"  # 按钮按下色（中灰）
        self.bg_frosted_selected = "#0d6efd"  # 按钮选中色（蓝色）
        self.bg_search = "#e9ecef"  # 搜索框背景色（比原来深一点）
        self.fg_primary = "#212529"  # 主文字色（深灰黑）
        self.fg_secondary = "#495057"  # 次要文字色（中灰）

        self.configure(bg=self.bg_primary)

        # ---------- iPhone 17风格字体定义（全部加粗，全局统一） ----------
        self.title_font = ("SF Pro Display", 28, "bold")  # 标题字体（加粗）
        self.subtitle_font = ("SF Pro Display", 13, "bold")  # 副标题字体（加粗）
        self.label_font = ("SF Pro Display", 14, "bold")  # 标签字体（加粗）
        self.button_font = ("SF Pro Display", 13, "bold")  # 按钮字体（加粗）
        self.entry_font = ("SF Pro Display", 13, "bold")  # 输入框字体（加粗）
        self.tree_content_font = ("SF Pro Display", 13, "bold")  # 表格内容字体（加粗）
        self.az_button_font = ("SF Pro Display", 14, "bold")  # 字母按钮字体（加粗，备用）
        self.az_title_font = ("SF Pro Display", 16, "bold")  # 字母标题字体（加粗，备用")

        # 价目表标题字体（比原来小一点）
        self.price_title_font = ("SF Pro Display", 18, "bold")  # 从28调小到18

        # 备选字体（加粗）
        self.fallback_fonts = [
            ("Segoe UI", "bold"),
            ("Helvetica Neue", "bold"),
            ("Arial", "bold"),
            ("TkDefaultFont", "bold")
        ]

        # ---------- 样式（全局统一） ----------
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # Treeview样式 - 白底黑字适配（加粗字体，全局统一）
        self.style.configure("Treeview.Heading",
                             background=self.bg_frosted, foreground=self.fg_primary,
                             relief="flat", font=self.label_font, borderwidth=0)
        self.style.configure("Treeview",
                             background=self.bg_surface, foreground=self.fg_primary,
                             fieldbackground=self.bg_surface, rowheight=1,
                             borderwidth=0, relief="flat",
                             font=self.tree_content_font)
        self.style.map("Treeview",
                       background=[("selected", self.bg_frosted_hover)],
                       foreground=[("selected", self.fg_primary)])

        # 标签页样式
        self.style.configure("TNotebook", background=self.bg_primary, borderwidth=0)
        self.style.configure("TNotebook.Tab",
                             background=self.bg_frosted,
                             foreground=self.fg_primary,
                             padding=[10, 5],
                             font=self.button_font)
        self.style.map("TNotebook.Tab",
                       background=[("selected", self.bg_frosted_selected),
                                   ("active", self.bg_frosted_hover)],
                       foreground=[("selected", "#ffffff"),
                                   ("active", self.fg_primary)])
        # ---------- 价目表字体测量（用于精确换行计算） ----------
        from tkinter import font as tkfont
        self._price_tree_font = tkfont.Font(family="SF Pro Display", size=13, weight="bold")
        self._price_unit_height = self._price_tree_font.metrics('linespace')  # 实际行高（像素）
        self._price_prev_col_widths = {}  # 上次列宽快照，用于检测列宽变化
        self._price_row_lines = 3  # 默认显示 3 行文字
        self._price_cache_key = None  # (company_name, pricing_type) 缓存键

        # ---------- 主容器 ----------
        self.main_container = tk.Frame(self, bg=self.bg_primary)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # ---------- 顶部 banner（紧凑版：小 logo + 语言切换，无标题文字） ----------
        banner = tk.Frame(self.main_container, bg=self.bg_primary)
        banner.pack(fill="x", pady=(0, 4))

        # 小 logo（高度缩至 36px）
        try:
            logo_path = get_resource_path(os.path.join("images", "seastarEngineLogo.png"))
            img = Image.open(logo_path).convert("RGBA")
            logo_height = 36
            logo_width = int(img.width * logo_height / img.height)
            img = img.resize((logo_width, logo_height), Image.LANCZOS)
            self.logo = ImageTk.PhotoImage(img, master=self)
            tk.Label(banner, image=self.logo, bg=self.bg_primary).pack(side="left", padx=(6, 12), pady=2)
        except Exception as e:
            logging.error(f"加载logo失败: {e}")
            tk.Label(banner, text="●", bg=self.bg_primary, fg="#0d6efd",
                     font=("SF Pro Display", 20, "bold")).pack(side="left", padx=(6, 12), pady=2)

        # 保留 top_btn_config 供搜索按钮使用
        top_btn_config = {
            "bg": self.bg_frosted,
            "fg": self.fg_primary,
            "hover_bg": self.bg_frosted_hover,
            "active_bg": self.bg_frosted_active,
            "selected_bg": self.bg_frosted_selected,
            "selected_fg": "#ffffff",
            "font": ("SF Pro Display", 11, "bold"),
            "corner_radius": 6
        }

        # 右侧区域：EN按钮 + 关键词选择器
        right_bar = tk.Frame(banner, bg=self.bg_primary)
        right_bar.pack(side="right", padx=6, anchor="ne")

        # 关键词选择器（EN按钮左侧，使用左右小按钮分页查看剩余关键词）
        kp_w = max(400, int(self.screen_width * 0.50))
        kp_outer = tk.Frame(right_bar, bg=self.bg_primary, width=kp_w + 44, height=28)
        kp_outer.pack(side="right", padx=(0, 4), pady=2, anchor="n")
        kp_outer.pack_propagate(False)
        kp_outer.grid_propagate(False)

        _arrow_cfg = dict(
            bg=self.bg_frosted, fg=self.fg_primary,
            font=("SF Pro Display", 9, "bold"),
            relief="flat", cursor="hand2",
            width=2, height=1, padx=0, pady=0, bd=0,
            activebackground=self.bg_frosted_hover,
            activeforeground=self.fg_primary,
            highlightthickness=0
        )
        kp_outer.grid_columnconfigure(0, minsize=22, weight=0)
        kp_outer.grid_columnconfigure(1, weight=1)
        kp_outer.grid_columnconfigure(2, minsize=22, weight=0)
        kp_outer.grid_rowconfigure(0, minsize=28, weight=0)

        self._kp_left_btn = tk.Button(
            kp_outer,
            text="◀",
            command=lambda: self._shift_keyword_page(-1),
            state="disabled",
            **_arrow_cfg,
        )
        self._kp_left_btn.grid(row=0, column=0, padx=(0, 2), pady=2)

        self._kp_container = tk.Frame(kp_outer, bg=self.bg_primary, height=28)
        self._kp_container.grid(row=0, column=1, sticky="nsew")
        self._kp_container.grid_propagate(False)
        self._kp_container.bind("<Configure>", self._on_keyword_picker_resize)

        self._kp_right_btn = tk.Button(
            kp_outer,
            text="▶",
            command=lambda: self._shift_keyword_page(1),
            state="disabled",
            **_arrow_cfg,
        )
        self._kp_right_btn.grid(row=0, column=2, padx=(2, 0), pady=2)

        self._kp_inner = tk.Frame(self._kp_container, bg=self.bg_primary, height=28)
        self._kp_inner.pack(fill="both", expand=True)

        # ---------- 搜索条（紧凑，直接跟在 banner 下方） ----------
        self.search_bar = tk.Frame(self.main_container, bg=self.bg_primary)
        self.search_bar.pack(fill="x", pady=(0, 4))

        # 关键词选择器初始化
        self._keyword_btns = {}
        self._keyword_selected = set()
        self._pending_search_keyword = None

        # ★ 打包顺序：右侧元素先 pack，左侧 entry 最后 pack（fill=x 才能填满剩余空间）

        # 搜索按钮（最右，小尺寸）
        self.search_button = RoundedButton(self.search_bar, text="搜索", command=self.on_search_button_click,
                                           width=52, height=26, **top_btn_config)
        self.search_button.pack(side="right", padx=(4, 0))

        # 搜索标签（最左，小号）
        self.search_label = tk.Label(self.search_bar, text="搜索", bg=self.bg_primary,
                                     fg=self.fg_secondary, font=("SF Pro Display", 11, "bold"))
        self.search_label.pack(side="left")

        # 搜索输入框
        self.search_var = tk.StringVar()
        self._search_trace_id = self.search_var.trace_add("write", self.on_search_change)
        self.search_entry = tk.Entry(self.search_bar, textvariable=self.search_var,
                                     font=("SF Pro Display", 11, "bold"),
                                     bg=self.bg_search, fg=self.fg_primary,
                                     insertbackground=self.fg_primary, relief="flat", borderwidth=1)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=4)

        # 回车键只绑定在 Entry 本身，避免全局绑定持续触发空搜索
        self.search_entry.bind('<Return>', self.on_search_enter)

        # ---------- 主内容区 ----------
        self.content_container = tk.Frame(self.main_container, bg=self.bg_primary)
        self.content_container.pack(fill="both", expand=True)

        # ---------- 价目表界面（默认显示） ----------
        self.price_frame = tk.Frame(self.content_container, bg=self.bg_primary)

        # 公司名 + 价格类型：同一行（紧凑）
        company_info_row = tk.Frame(self.price_frame, bg=self.bg_primary)
        company_info_row.pack(fill="x", pady=(2, 2))

        self.company_label = tk.Label(company_info_row, bg=self.bg_primary,
                                      fg=self.fg_primary,
                                      font=("SF Pro Display", 13, "bold"))
        self.company_label.pack(side="left", padx=(0, 12))

        self.price_type_label = tk.Label(company_info_row, bg=self.bg_primary,
                                         fg=self.fg_secondary,
                                         font=("SF Pro Display", 11))
        self.price_type_label.pack(side="left")

        # 客户商品信息标签（显示传入的商品代码和客户描述，默认不 pack）
        self._customer_info_label = tk.Label(
            self.price_frame, text="",
            bg="#fff8e1", fg="#5a3e00",
            font=self.subtitle_font,
            anchor="w", justify="left", wraplength=1400, padx=10, pady=5
        )
        # _customer_info_label 初始不 pack，需要时用 pack(before=...) 动态插入

        # 定位状态（默认激活）
        self._locate_active = True
        self._last_locate_keyword = None

        # 行高控制 + 搜索导航：合并一行（极紧凑）
        ctrl_nav_frame = tk.Frame(self.price_frame, bg=self.bg_primary)
        ctrl_nav_frame.pack(fill="x", pady=(1, 2))

        _sf = ("SF Pro Display", 10, "bold")  # 小号字体复用
        _btn = dict(font=_sf, bg=self.bg_frosted, fg=self.fg_primary,
                    relief="flat", cursor="hand2", padx=3, pady=0)

        self._lbl_rowheight = tk.Label(ctrl_nav_frame, text="行高", bg=self.bg_primary,
                                       fg=self.fg_secondary, font=_sf)
        self._lbl_rowheight.pack(side="left", padx=(0, 2))
        tk.Button(ctrl_nav_frame, text="－",
                  command=lambda: self._change_price_row_lines(-1),
                  width=2, **_btn).pack(side="left")
        self._row_lines_label = tk.Label(ctrl_nav_frame, text="3行",
                                         bg=self.bg_primary, fg=self.fg_primary,
                                         font=_sf, width=3)
        self._row_lines_label.pack(side="left", padx=2)
        tk.Button(ctrl_nav_frame, text="＋",
                  command=lambda: self._change_price_row_lines(1),
                  width=2, **_btn).pack(side="left")

        # 分隔
        tk.Frame(ctrl_nav_frame, bg=self.bg_frosted, width=1).pack(
            side="left", fill="y", padx=6, pady=2)

        self.price_search_stats_label = tk.Label(
            ctrl_nav_frame, text="", bg=self.bg_primary,
            fg=self.fg_secondary, font=_sf, anchor="w"
        )
        self.price_search_stats_label.pack(side="left", fill="x", expand=True)

        tk.Button(ctrl_nav_frame, text="▲", command=self.find_prev_match_price,
                  **_btn).pack(side="left", padx=(0, 2))
        tk.Button(ctrl_nav_frame, text="▼", command=self.find_next_match_price,
                  **_btn).pack(side="left", padx=(0, 2))
        self._btn_clear_search = tk.Button(ctrl_nav_frame, text="✕清除",
                                           command=self.clear_price_search, **_btn)
        self._btn_clear_search.pack(side="left", padx=(0, 6))

        self._kp_clear_btn = tk.Button(
            ctrl_nav_frame, text="✕关键词",
            command=self._clear_keyword_picker,
            font=_sf, bg=self.bg_frosted, fg=self.fg_secondary,
            relief="flat", cursor="hand2", padx=3, pady=0
        )
        self._kp_clear_btn.pack(side="right", padx=(3, 0))

        self._locate_btn = tk.Button(
            ctrl_nav_frame, text="📍定位",
            command=self._toggle_locate,
            font=_sf, bg=self.bg_frosted_selected, fg="#ffffff",
            relief="flat", cursor="hand2", padx=5, pady=0
        )
        self._locate_btn.pack(side="right", padx=(3, 0))

        # Treeview容器 - 外框提供 1px 深色边框，内框使用 Grid 布局支持滚动条
        price_tree_border = tk.Frame(self.price_frame, bg="#909090", padx=1, pady=1)
        price_tree_border.pack(fill="both", expand=True)
        price_tree_frame = tk.Frame(price_tree_border, bg=self.bg_primary)
        price_tree_frame.pack(fill="both", expand=True)

        # 配置Grid布局权重
        price_tree_frame.grid_rowconfigure(0, weight=1)
        price_tree_frame.grid_columnconfigure(0, weight=1)

        # 价目表列（初始用默认列，show_price_list 会动态重建）
        self.price_cols = FL_DISPLAY[:25]  # 默认：0-22 固定 + High/Medium Price
        self._current_company_name = ""  # 记录当前公司名，用于缓存判断

        self.price_tree = ttk.Treeview(price_tree_frame, columns=self.price_cols,
                                       show="headings", selectmode="browse")

        # 列可见性与 BooleanVar（动态列，初始全部可见）
        self.price_col_visible = {col: True for col in self.price_cols}
        self.column_vars = {col: tk.BooleanVar(value=True) for col in self.price_cols}

        # 为价目表Treeview配置标签样式
        self.price_tree.tag_configure('matched', background="#0d6efd", foreground="#ffffff",
                                      font=self.tree_content_font)
        self.price_tree.tag_configure('normal', background=self.bg_surface, foreground=self.fg_primary,
                                      font=self.tree_content_font)

        # eng2chn：FL_DISPLAY 本身即中文显示名，透传即可
        self.eng2chn = {d: d for d in FL_DISPLAY}
        self.col_widths = FL_COL_WIDTHS.copy()

        for c in self.price_cols:
            self.price_tree.heading(c, text=c)
            self.price_tree.column(c, width=self.col_widths.get(c, 110),
                                   anchor="w", minwidth=50, stretch=False)
            # 松手后触发重算（检测列宽拖拽）
        self.price_tree.bind('<ButtonRelease-1>', self._on_price_header_release)
        self.after(150, self._init_price_col_widths)

        # 将Treeview放在Grid中
        self.price_tree.grid(row=0, column=0, sticky="nsew")

        # 垂直滚动条
        price_vsb = ttk.Scrollbar(price_tree_frame, orient="vertical", command=self.price_tree.yview)
        price_vsb.grid(row=0, column=1, sticky="ns")
        self.price_tree.configure(yscrollcommand=price_vsb.set)

        # 水平滚动条 - 新增底部水平滚动条
        price_hsb = ttk.Scrollbar(price_tree_frame, orient="horizontal", command=self.price_tree.xview)
        price_hsb.grid(row=1, column=0, sticky="ew")
        self.price_tree.configure(xscrollcommand=price_hsb.set)

        # 绑定右键菜单到表头
        self.price_tree.bind("<Button-3>", self.show_price_column_menu)

        # 绑定双击事件
        self.price_tree.bind('<Double-Button-1>', self.on_price_tree_double_click)

        # ---------- 全局搜索界面 ----------
        self.global_search_frame = tk.Frame(self.content_container, bg=self.bg_primary)

        # 全局搜索标题
        self.global_search_title = tk.Label(self.global_search_frame, text="全局搜索",
                                            bg=self.bg_primary, fg=self.fg_primary, font=self.price_title_font)
        self.global_search_title.pack(fill="x", pady=(0, 10))

        # 搜索统计标签
        self.result_stats_label = tk.Label(self.global_search_frame, text="输入关键词后按回车或点击搜索按钮",
                                           bg=self.bg_primary, fg=self.fg_secondary, font=self.subtitle_font,
                                           justify="left", anchor="w")
        self.result_stats_label.pack(fill="x", pady=(0, 10), padx=5)

        # 创建标签页容器
        self.global_notebook = ttk.Notebook(self.global_search_frame)
        self.global_notebook.pack(fill="both", expand=True)

        # 存储标签页和Treeview的引用
        self.global_tabs = {}  # {表名: (frame, treeview)}

        # 初始隐藏全局搜索界面
        self.global_search_frame.pack_forget()

        # 默认显示空价目表
        self.show_price_list("", "H")

        # ========== 全局搜索高亮系统 ==========
        self.highlighter = GlobalSearchHighlighter(self)

    def on_price_tree_double_click(self, event):
        """处理价目表行的双击事件"""
        # 获取选中的行
        selection = self.price_tree.selection()
        if not selection:
            return

        selected_item = selection[0]
        values = self.price_tree.item(selected_item, 'values')

        # 构建返回的数据
        columns = self.price_cols
        row_data = {}
        for i, col in enumerate(columns):
            if i < len(values):
                row_data[col] = values[i]

        # 调用回调函数传递数据
        if self.price_tree_select_callback:
            self.price_tree_select_callback(row_data)
            # 隐藏窗口，但保留实例以供下次使用
            self.hide_window()
            # 清除回调引用，避免重复调用
            self.price_tree_select_callback = None

    def clear_blue_highlights(self):
        """清除蓝色高亮"""
        if not hasattr(self, 'price_tree') or not self.price_tree.winfo_exists():
            self.blue_highlight_items = []
            self.blue_highlight_keyword = ""
            return

        try:
            # 获取当前所有有效项目
            current_items = list(self.price_tree.get_children())

            # 只处理当前存在的项目
            for item in self.blue_highlight_items[:]:  # 创建副本，避免修改迭代中的列表
                try:
                    if item in current_items:
                        self._set_price_item_tags(item)
                    else:
                        # 从列表中移除不存在的项目
                        self.blue_highlight_items.remove(item)
                except Exception as e:
                    logging.debug(f"清除蓝色高亮项目 {item} 时出错: {e}")
                    continue

        except Exception as e:
            logging.error(f"清除蓝色高亮时出错: {e}")
        finally:
            # 确保重置相关属性
            self.blue_highlight_keyword = ""
            # 注意：不清空 self.blue_highlight_items，因为我们可能已经移除了不存在的项目

    def on_search_enter(self, event=None):
        """处理搜索框的回车键事件"""
        # 同步 Entry → StringVar，防止绑定断开时 search_price_list 读到空值
        current_text = self.search_entry.get()
        if self.search_var.get() != current_text:
            self.search_var.set(current_text)
        if self.current_view == 'global_search':
            self.perform_global_search()
        elif self.current_view == 'price':
            self.search_price_list()

    def show_global_search(self):
        """显示全局搜索界面"""
        self.current_view = 'global_search'

        # 更新搜索标签
        self.search_label.config(text="全局搜索:")

        # 隐藏其他界面
        self.price_frame.pack_forget()

        # 显示全局搜索界面
        self.global_search_frame.pack(fill="both", expand=True)

        # 更新标题和提示
        self.global_search_title.config(text="全局搜索")
        self.result_stats_label.config(text="输入搜索关键词后按回车或点击搜索按钮\n支持F3/Shift+F3导航匹配项")

        # 将焦点设置到搜索框
        self.search_entry.focus_set()
        self.search_entry.icursor(0)

    def perform_global_search(self, event=None):
        """执行全局搜索"""
        keyword = self.search_entry.get().strip()

        if not keyword:
            self.highlighter.clear_all_highlights()
            self.result_stats_label.config(text="请输入搜索关键词\n支持F3/Shift+F3导航匹配项")
            return

        # 清空之前的搜索结果
        self.clear_global_search_results()

        # 显示搜索中状态
        self.global_search_title.config(text=f"全局搜索: {keyword}")
        self.result_stats_label.config(text="正在搜索所有表中的匹配项...")
        self.update()

        # 执行数据库搜索（带结果限制，避免性能问题）
        search_results = search_all_tables_with_limit(keyword, limit_per_table=500)

        if not search_results:
            self.result_stats_label.config(text=f"未找到包含 '{keyword}' 的结果\n支持F3/Shift+F3导航匹配项")
            return

        # 为每个有结果的表创建标签页
        for table_name, (columns, rows) in search_results.items():
            self.create_table_tab(table_name, columns, rows)

        # 设置第一个标签页为选中状态
        if self.global_notebook.tabs():
            self.global_notebook.select(self.global_notebook.tabs()[0])

        # 执行带高亮的搜索（仅高亮匹配项）
        self.highlighter.perform_highlighted_search(keyword)

    def create_table_tab(self, table_name: str, columns: List[str], data: List[Tuple]):
        """为指定表创建标签页和Treeview（初始全部正常显示）"""
        # 创建Frame作为标签页内容
        tab_frame = tk.Frame(self.global_notebook, bg=self.bg_primary)

        # 配置Grid布局
        tab_frame.grid_rowconfigure(0, weight=1)
        tab_frame.grid_columnconfigure(0, weight=1)

        # 创建Treeview
        tree = ttk.Treeview(tab_frame, columns=columns, show="headings", selectmode="browse")

        # 配置高亮标签样式（仅匹配项高亮）
        self.highlighter.setup_tree_tags(tree)

        # 设置列标题和宽度
        for i, col in enumerate(columns):
            # 尝试获取列的中文显示名
            display_name = self.eng2chn.get(col, col)
            tree.heading(col, text=display_name)

            # 设置列宽度（动态计算）
            col_width = self.get_column_width(col, data, i)
            tree.column(col, width=col_width, anchor="w", minwidth=80)

        # 将Treeview放在Grid中
        tree.grid(row=0, column=0, sticky="nsew")

        # 垂直滚动条
        vsb = ttk.Scrollbar(tab_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)

        # 水平滚动条
        hsb = ttk.Scrollbar(tab_frame, orient="horizontal", command=tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        tree.configure(xscrollcommand=hsb.set)

        # 添加标签页（显示表名和结果数）
        display_name = get_table_display_name(table_name)
        tab_text = f"{display_name} ({len(data)}条结果)"
        self.global_notebook.add(tab_frame, text=tab_text)

        # 填充数据（初始无标签，完全继承默认样式）
        self.populate_treeview_with_data(tree, columns, data)

        # 存储引用
        self.global_tabs[table_name] = (tab_frame, tree)

    def get_column_width(self, column_name: str, data: List[Tuple], column_index: int) -> int:
        """根据列名和数据动态计算列宽度"""
        # 预设宽度（全局统一）
        preset_widths = {
            "SS_U8_Code": 140,
            "SS_IMPA_Code": 140,
            "C_Company_Code": 120,
            "C_Company_Name": 200,
            "SS_Description": 220,
            "SS_Details": 220,
            "SS_Offer": 160,
            "SS_Remark": 160,
            "SS_Unit": 100,
            "Price": 140,
            "SS_Price_H": 100,
            "SS_Price_M": 100,
            "SS_Price_L": 100,
            "C_Pricing_Type": 80,
            "SS_No": 80,
        }

        # 如果列名在预设中，使用预设宽度
        if column_name in preset_widths:
            return preset_widths[column_name]

        # 否则根据列名长度和数据内容计算宽度
        base_width = len(column_name) * 9  # 每个字符约9像素

        # 检查数据中的最大长度（只检查前20行以提高性能）
        max_data_len = 0
        for row in data[:20]:
            if column_index < len(row):
                cell_value = str(row[column_index])
                max_data_len = max(max_data_len, len(cell_value))

        data_width = max_data_len * 7  # 每个字符约7像素

        return min(max(base_width, data_width, 100), 400)  # 限制在100-400像素之间

    def populate_treeview_with_data(self, tree: ttk.Treeview, columns: List[str], data: List[Tuple]):
        """向Treeview填充数据（所有项正常显示，匹配项高亮）"""
        for item in tree.get_children():
            tree.delete(item)

        for row in data:
            tree.insert("", "end", values=row, tags=('normal',))  # 插入所有项

    def highlight_in_tree(self, tree, keyword):
        """在Treeview中高亮匹配项"""
        all_items = tree.get_children()
        matched_items = []

        for item in all_items:
            values = tree.item(item, "values")
            is_matched = False

            for cell in values:
                cell_str = str(cell).strip().upper()
                if keyword in cell_str:
                    is_matched = True
                    break

            if is_matched:
                tree.item(item, tags=('matched',))  # 设置匹配项为高亮
                matched_items.append(item)
            else:
                tree.item(item, tags=('normal',))  # 非匹配项保持默认

        return matched_items

    def clear_global_search_results(self):
        """清空全局搜索结果"""
        # 删除所有标签页
        for tab_id in self.global_notebook.tabs():
            self.global_notebook.forget(tab_id)

        # 清空存储的引用
        self.global_tabs.clear()

        # 清除所有高亮和匹配状态
        self.highlighter.clear_all_highlights()

    def _init_price_col_widths(self):
        """初始化列宽快照"""
        try:
            self._price_prev_col_widths = {col: self.price_tree.column(col, 'width') for col in self.price_cols}
        except Exception:
            pass

    def _on_price_header_release(self, event):
        """用户松开鼠标时检查列宽是否变化，若有则重算换行和行高"""
        region = self.price_tree.identify_region(event.x, event.y)
        if region not in ('heading', 'separator'):
            return
        if not hasattr(self, '_price_prev_col_widths'):
            return
        try:
            current_widths = {col: self.price_tree.column(col, 'width') for col in self.price_cols}
        except Exception:
            return
        if current_widths != self._price_prev_col_widths:
            self._price_prev_col_widths = current_widths
            self._rewrap_price_cells()

    def _rewrap_price_cells(self):
        """列宽变化后重新计算所有单元格换行，并更新每行独立行高"""
        if not hasattr(self, 'price_data') or not self.price_data:
            return
        children = self.price_tree.get_children()
        if not children:
            return
        for i, item in enumerate(children):
            if i >= len(self.price_data):
                break
            original_row = self.price_data[i]
            wrapped_row = tuple(
                self._wrap_price_text(str(v) if v is not None else "", col_id)
                for v, col_id in zip(original_row, self.price_cols)
            )
            self.price_tree.item(item, values=wrapped_row)
            max_lines = max(
                (str(v).count('\n') + 1 for v in wrapped_row if v),
                default=1
            )
            self._apply_price_row_height(item, i)

    def _wrap_price_text(self, text, col_id):
        """按列宽换行，裁剪到 _price_row_lines 行，超出末行加省略号"""
        import textwrap
        if not text:
            return ""
        no_wrap = ["U8代码", "IMPA代码", "NO", "Brand Sort"]
        if col_id in no_wrap:
            return str(text)
        text = str(text)

        col_width = self.col_widths.get(col_id, 120)
        try:
            actual = self.price_tree.column(col_id, 'width')
            if actual > 0:
                col_width = actual
        except Exception:
            pass
        if col_width <= 4:
            col_width = 120

        usable_width = max(1, col_width - 4)  # 左右各 2px 边距
        if hasattr(self, '_price_tree_font'):
            avg_char_px = max(1, self._price_tree_font.measure('0'))
        else:
            avg_char_px = 8

        chars_per_line = max(4, int(usable_width / avg_char_px))
        lines = textwrap.wrap(text, width=chars_per_line)
        if not lines:
            return text

        cap = getattr(self, '_price_row_lines', 3)
        if len(lines) > cap:
            lines = lines[:cap]
            # 末行截断加省略号
            last = lines[-1]
            if len(last) >= chars_per_line:
                lines[-1] = last[:chars_per_line - 1] + '…'
            else:
                lines[-1] = last + '…'

        return '\n'.join(lines)

    def _apply_price_row_height(self, item_id, row_index, max_lines=None):
        """配置行颜色标签（行高由 _update_price_tree_height 统一管理，奇偶交替色）"""
        tag_name = f'prow_{row_index}'
        bg = "#ffffff" if row_index % 2 == 0 else "#eef2f7"
        self.price_tree.tag_configure(tag_name,
                                      background=bg,
                                      foreground=self.fg_primary,
                                      font=self.tree_content_font)
        self._price_item_heights[item_id] = tag_name
        return tag_name

    def _update_price_tree_height(self):
        """按当前 _price_row_lines 更新全局 rowheight"""
        line_h = getattr(self, '_price_unit_height', 18)
        cap = getattr(self, '_price_row_lines', 3)
        new_h = line_h * cap + 4  # 上下各 2px
        self.style.configure("Treeview", rowheight=new_h)

    def _change_price_row_lines(self, delta):
        """增减每行显示的文字行数（最少1行，最多10行），并重新渲染"""
        self._price_row_lines = max(1, min(10, getattr(self, '_price_row_lines', 3) + delta))
        self._update_price_tree_height()
        # 重新换行所有单元格以匹配新行数
        if hasattr(self, 'price_data') and self.price_data:
            children = self.price_tree.get_children()
            for i, item in enumerate(children):
                if i >= len(self.price_data):
                    break
                original_row = self.price_data[i]
                wrapped_row = tuple(
                    self._wrap_price_text(str(v) if v is not None else "", col_id)
                    for v, col_id in zip(original_row, self.price_cols)
                )
                self.price_tree.item(item, values=wrapped_row)
        # 更新按钮标签
        if hasattr(self, '_row_lines_label'):
            self._row_lines_label.config(text=f"{self._price_row_lines}行")

    def _set_price_item_tags(self, item, *highlight_tags):
        """设置价目表行的标签。
        ttk Treeview：tuple 末位 tag 优先级最高。
        prow_X（行底色）排首位，高亮 tag 排末位 → 高亮颜色胜出。"""
        height_tag = self._price_item_heights.get(item)
        if height_tag:
            if highlight_tags:
                self.price_tree.item(item, tags=(height_tag,) + highlight_tags)
            else:
                self.price_tree.item(item, tags=(height_tag,))
        else:
            self.price_tree.item(item, tags=highlight_tags if highlight_tags else ())

    def populate_price_tree(self, data: List[Tuple]):
        """填充价目表数据（每行独立行高 + 单元格自动换行）"""
        for item in self.price_tree.get_children():
            self.price_tree.delete(item)

        self.price_tree_items = []
        self.blue_highlight_items = []
        self.initial_highlight_items = []
        self._price_item_heights = {}

        # 预配置高亮标签——必须在 prow_X 之前配置，确保 prow_X 最后配置而优先级最高，
        # 但 item tags tuple 中 blue_highlight/search_highlight 排在最后，
        # ttk Treeview 以 tuple 中最后的 tag 为准
        self.price_tree.tag_configure('blue_highlight',
                                      background='#0d6efd',
                                      foreground='#ffffff',
                                      font=self.tree_content_font)
        self.price_tree.tag_configure('search_highlight',
                                      background='#ffc107',
                                      foreground='#212529',
                                      font=self.tree_content_font)

        for i, row in enumerate(data):
            # 对每个单元格按列宽换行
            wrapped_row = tuple(
                self._wrap_price_text(str(v) if v is not None else "", col_id)
                for v, col_id in zip(row, self.price_cols)
            )
            # 从已换行的内容计算该行实际行数
            max_lines = max(
                (str(v).count('\n') + 1 for v in wrapped_row if v),
                default=1
            )
            item_id = self.price_tree.insert("", "end", values=wrapped_row)
            self.price_tree_items.append(item_id)
            tag_name = self._apply_price_row_height(item_id, i)
            self.price_tree.item(item_id, tags=(tag_name,))

        # 重新应用列可见性
        for col_id, is_visible in self.price_col_visible.items():
            if not is_visible:
                self.price_tree.column(col_id, width=0, minwidth=0, stretch=False)
            else:
                width = self.col_widths.get(col_id, 120)
                self.price_tree.column(col_id, width=width, minwidth=60, stretch=False)
        # 统一设置行高
        self._update_price_tree_height()

    def on_search_change(self, *_):
        """搜索框内容变化——价目表和全局搜索均不实时触发"""
        logging.debug(f"[on_search_change] search_var='{self.search_var.get()}'")

    def find_prev_match_price(self, event=None):
        """跳转到上一个搜索结果"""
        if hasattr(self, 'price_matched_items') and self.price_matched_items:
            self._goto_price_match(
                getattr(self, 'price_current_match_index', 0) - 1)

    def search_prices(self):
        """兼容旧调用"""
        self.search_price_list()

    # ==================== 价目表搜索 ====================

    def on_search_button_click(self):
        """搜索按钮路由：价目表 or 全局搜索"""
        # 主动将 Entry 内容同步回 StringVar，防止 textvariable 绑定断开时漏读
        current_text = self.search_entry.get()
        if self.search_var.get() != current_text:
            self.search_var.set(current_text)
        logging.debug(f"[on_search_button_click] entry='{current_text}'，var='{self.search_var.get()}'")
        if self.current_view == 'price':
            self.search_price_list()
        else:
            self.perform_global_search()
        self.search_entry.focus_set()

    def search_price_list(self):
        """在价目表中搜索：用原始 price_data 做全列子串匹配（避免显示截断干扰），
        Description/Details/Offer 权重×3，其余列权重×1，按总分降序排列。"""
        import re as _re
        raw = self.search_entry.get().strip()

        # ★ 合并关键词按钮选中项（与搜索栏互相独立，搜索时合并）
        if self._keyword_selected:
            kp_part = ",".join(self._keyword_selected)
            raw = (raw + "," + kp_part) if raw else kp_part

        logging.debug(
            f"[search_price_list] 触发搜索 | search_var='{self.search_var.get()}' "
            f"| entry.get()='{self.search_entry.get()}' "
            f"| raw='{raw}' | _keyword_selected={self._keyword_selected}"
        )
        # 先按逗号/分号分割，再对每段按空格分割，合并去重
        _parts = _re.split(r'[,;，；]', raw)
        _seen_kw = set()
        keywords = []
        for _p in _parts:
            for _w in _p.split():
                _w = _w.strip().upper()
                if _w and _w not in _seen_kw:
                    _seen_kw.add(_w)
                    keywords.append(_w)

        if not keywords:
            self.clear_price_search()
            return

        if not hasattr(self, 'price_tree') or not self.price_tree.winfo_exists():
            return

        if not hasattr(self, 'price_data') or not self.price_data:
            return

        current_items = list(self.price_tree.get_children())
        if not current_items:
            return

        # 确保高亮标签已配置
        self.price_tree.tag_configure('search_highlight',
                                      background='#ffc107',
                                      foreground='#212529',
                                      font=self.tree_content_font)
        self._clear_price_search_highlights()

        col_weights = {
            "SS_U8_Code":     1,
            "SS_IMPA_Code":   1,
            "SS_Description": 3,
            "SS_Details":     3,
            "SS_Offer":       3,
            "SS_Remark":      2,
            "SS_Unit":        1,
            "Price":          1,
        }

        scored = []
        for i, item in enumerate(current_items):
            if i >= len(self.price_data):
                break
            # ★ 用原始未截断数据做匹配，不受 Treeview 显示文本影响
            original_row = self.price_data[i]
            total_score = 0
            for ci, col_id in enumerate(self.price_cols):
                if ci >= len(original_row):
                    continue
                cell = str(original_row[ci]).upper() if original_row[ci] is not None else ""
                if not cell:
                    continue
                weight = col_weights.get(col_id, 1)
                for kw in keywords:
                    cnt = cell.count(kw)
                    total_score += cnt * weight
            if total_score > 0:
                scored.append((total_score, item))

        scored.sort(key=lambda x: -x[0])
        matched_items = [item for _, item in scored]

        for item in matched_items:
            cur_tags = list(self.price_tree.item(item, "tags"))
            if 'search_highlight' not in cur_tags:
                cur_tags.append('search_highlight')
                self.price_tree.item(item, tags=tuple(cur_tags))

        self.price_matched_items = matched_items
        self.price_current_match_index = 0

        if matched_items:
            self._goto_price_match(0)
        else:
            display_kw = self.search_var.get().strip() or "（仅关键词按钮）"
            if hasattr(self, 'price_search_stats_label'):
                self.price_search_stats_label.config(
                    text=f"未找到含 '{display_kw}' 的内容（共搜索 {len(keywords)} 个关键词）")

    def _goto_price_match(self, index):
        """跳转到第 index 个搜索结果"""
        if not hasattr(self, 'price_matched_items') or not self.price_matched_items:
            return
        self.price_current_match_index = index % len(self.price_matched_items)
        item = self.price_matched_items[self.price_current_match_index]
        self.price_tree.selection_set(item)
        self.price_tree.see(item)
        try:
            all_items = self.price_tree.get_children()
            if all_items:
                idx = list(all_items).index(item)
                self.price_tree.yview_moveto(max(0, (idx - 2) / len(all_items)))
        except (ValueError, Exception):
            pass  # item 不在树中时安全跳过，不影响后续逻辑
        self._update_price_search_stats()

    def _update_price_search_stats(self):
        """更新搜索结果统计标签"""
        if not hasattr(self, 'price_search_stats_label'):
            return
        if not hasattr(self, 'price_matched_items') or not self.price_matched_items:
            self.price_search_stats_label.config(text="")
            return
        cur = self.price_current_match_index + 1
        total = len(self.price_matched_items)
        self.price_search_stats_label.config(
            text=f"找到 {total} 个结果，当前第 {cur} 个  （回车 / ▼▲ 导航）")

    def _clear_price_search_highlights(self):
        """清除橙色搜索高亮（保留蓝色初始高亮）"""
        if not hasattr(self, 'price_tree') or not self.price_tree.winfo_exists():
            return
        for item in self.price_tree.get_children():
            try:
                tags = list(self.price_tree.item(item, "tags"))
                if 'search_highlight' in tags:
                    tags.remove('search_highlight')
                    self.price_tree.item(item, tags=tuple(tags))
            except Exception:
                pass

    def clear_price_search(self):
        """清除搜索状态（橙色高亮 + 导航状态 + 统计标签）"""
        self._clear_price_search_highlights()
        self.price_matched_items = []
        self.price_current_match_index = 0
        if hasattr(self, 'price_search_stats_label'):
            self.price_search_stats_label.config(text="")

    def _safe_initial_locate(self, keyword):
        """安全执行初始定位：若搜索栏已有内容则跳过，避免覆盖用户输入"""
        if self.search_var.get().strip():
            return  # 用户已输入内容，不自动定位
        if not getattr(self, '_locate_active', True):
            return  # 定位按钮已关闭
        self.perform_initial_search(keyword)

    def _toggle_locate(self):
        """切换定位按钮：亮起=蓝色高亮定位，暗淡=清除蓝色高亮"""
        self._locate_active = not self._locate_active
        if self._locate_active:
            self._locate_btn.config(bg=self.bg_frosted_selected, fg="#ffffff")
            kw = getattr(self, '_last_locate_keyword', None)
            if kw:
                self.perform_initial_search(kw)
        else:
            self._locate_btn.config(bg=self.bg_frosted, fg=self.fg_primary)
            self.clear_blue_highlights()

    def find_next_match_price(self, event=None):
        """跳转到下一个搜索结果"""
        if hasattr(self, 'price_matched_items') and self.price_matched_items:
            self._goto_price_match(
                getattr(self, 'price_current_match_index', 0) + 1)

    def show_price_list(self, company_name: str, pricing_type: str = ""):
        """显示价目表界面，按公司名动态选择价格列"""
        self.current_view = 'price'
        self.search_label.config(text="Search:")
        self.global_search_frame.pack_forget()
        self.price_frame.pack(fill="both", expand=True)

        # 更新顶部标签
        self.company_label.config(
            text=company_name if company_name else "价目表",
            font=self.price_title_font)
        col_idx = _determine_company_col_idx(company_name)
        if col_idx is not None:
            price_desc = f"Price: {FL_DISPLAY[col_idx]}"
        else:
            price_desc = "Price: High Price / Medium Price"
        self.price_type_label.config(text=price_desc)

        # 缓存判断：公司名变化才重新加载数据
        cache_hit = (company_name == self._current_company_name and
                     hasattr(self, 'price_data') and bool(self.price_data))

        if not cache_hit:
            self._current_company_name = company_name

            # 取数据
            new_cols, data = fetch_fulllist_for_price_view(company_name)

            # 重建 Treeview 列
            self.price_cols        = new_cols
            self.price_col_visible = {col: True for col in new_cols}
            self.column_vars       = {col: tk.BooleanVar(value=True) for col in new_cols}
            self.col_widths        = FL_COL_WIDTHS.copy()
            self.eng2chn           = {d: d for d in FL_DISPLAY}

            self.price_tree.config(columns=new_cols)
            for c in new_cols:
                self.price_tree.heading(c, text=c)
                self.price_tree.column(c, width=self.col_widths.get(c, 110),
                                       anchor="w", minwidth=50, stretch=False)

            # 构建 price_data（加 $ 前缀到价格列）
            price_col_positions = [
                i for i, name in enumerate(new_cols)
                if name in (FL_DISPLAY[22:32])
            ]
            self.price_data = []
            for row in data:
                row_list = list(row)
                for pi in price_col_positions:
                    if pi < len(row_list) and row_list[pi]:
                        v = str(row_list[pi]).strip()
                        if v and not v.startswith('$'):
                            row_list[pi] = f"${v}"
                self.price_data.append(tuple(row_list))

            # 清除旧数据
            for item in self.price_tree.get_children():
                self.price_tree.delete(item)
            self.price_tree_items      = []
            self.blue_highlight_items  = []
            self.initial_highlight_items = []

            self.populate_price_tree(self.price_data)

        # 重置搜索状态
        self.search_entry.delete(0, 'end')
        self.search_var.set("")
        self.initial_search_keyword = None
        self.clear_blue_highlights()
        self.blue_highlight_keyword = ""
        self.blue_highlight_items   = []
        self.clear_price_search()

        self.bind('<F3>',       self.find_next_match_price)
        self.bind('<Shift-F3>', self.find_prev_match_price)

        self.search_entry.focus_set()
        self.search_entry.icursor(0)
        self.lift()
        self.focus_force()

        if hasattr(self, 'initial_search_keyword') and self.initial_search_keyword:
            self.after(300, lambda: self.perform_initial_search(self.initial_search_keyword))

    def refresh_lang(self):
        """由 price_query_tool 的语言切换按钮调用，刷新价目表窗口的前端文字。"""
        from translate import t as _t

        # ── 搜索标签 & 按钮 ──────────────────────────────────────────────────
        if self.current_view == 'price':
            self.search_label.config(text=_t("搜索:"))
        elif self.current_view == 'global_search':
            self.search_label.config(text=_t("全局搜索:"))

        try:
            self.search_button.update_text(_t("搜索"))
        except Exception:
            pass

        # ── 价目表列表头（只翻译显示文字，列 ID 不变） ──────────────────────
        for c in self.price_cols:
            try:
                self.price_tree.heading(c, text=_t(c))
            except Exception:
                pass

        # ── 行高控制区 ───────────────────────────────────────────────────────
        try:
            self._lbl_rowheight.config(text=_t("行高"))
        except Exception:
            pass

        try:
            lines = getattr(self, '_price_row_lines', 3)
            suffix = "行" if _t("行高") == "行高" else "rows"
            self._row_lines_label.config(text=f"{lines}{suffix}")
        except Exception:
            pass

        try:
            self._btn_clear_search.config(text=_t("✕清除"))
        except Exception:
            pass

        try:
            self._kp_clear_btn.config(text=_t("✕关键词"))
        except Exception:
            pass

        try:
            self._locate_btn.config(text=_t("📍定位"))
        except Exception:
            pass

    def open_stock_window(self):
        """打开库存窗口"""
        lang = "zh" if self.t("search") == "搜索" else "en"
        StockWindow = import_window_module("stock_window", "StockWindow")
        self.stock_window = StockWindow(self, lang, on_lang_change=self.set_lang_from_stock)
        self.stock_window.protocol("WM_DELETE_WINDOW", self.on_stock_close)

    def set_lang_from_stock(self, lang: str):
        """从库存窗口设置语言"""
        self.set_lang(lang)
        self.relabel_ui()
        self.lang_btn.update_text("中" if lang == "en" else "EN")

    def on_stock_close(self):
        """关闭库存窗口"""
        if hasattr(self, "stock_window"):
            self.stock_window.destroy()
            del self.stock_window

    def show_price_column_menu(self, event):
        """右键表头：动态显示当前所有列的勾选菜单"""
        if self.current_view != 'price':
            return
        region = self.price_tree.identify_region(event.x, event.y)
        if region != "heading":
            return

        menu = tk.Menu(self, tearoff=0)
        for col_id in self.price_cols:
            if col_id not in self.column_vars:
                self.column_vars[col_id] = tk.BooleanVar(value=True)
            menu.add_checkbutton(
                label=col_id,
                variable=self.column_vars[col_id],
                command=lambda c=col_id: self.toggle_price_column(c)
            )
        menu.tk_popup(event.x_root, event.y_root)

    def toggle_price_column(self, col_id: str):
        """切换价目表列显示"""
        is_visible = self.price_col_visible[col_id]

        if is_visible:
            self.price_tree.column(col_id, width=0, minwidth=0, stretch=False)
            self.price_col_visible[col_id] = False
            self.column_vars[col_id].set(False)
            logging.debug(f"隐藏列: {col_id}")
        else:
            width = self.col_widths.get(col_id, 120)
            self.price_tree.column(col_id, width=width, minwidth=60, stretch=False)
            self.price_col_visible[col_id] = True
            self.column_vars[col_id].set(True)
            logging.debug(f"显示列: {col_id}")

        self.price_tree.bind("<Button-3>", self.show_price_column_menu)

    def _get_keyword_page_size(self):
        """根据关键词区域宽度估算单页可显示的关键词按钮数量"""
        if not hasattr(self, '_kp_container'):
            return 1
        self._kp_container.update_idletasks()
        container_width = max(1, self._kp_container.winfo_width())
        return max(1, container_width // 95)

    def _render_keyword_picker(self):
        """按当前页重新渲染关键词按钮"""
        if not hasattr(self, '_kp_inner'):
            return

        for w in self._kp_inner.winfo_children():
            w.destroy()
        self._keyword_btns = {}

        keywords = getattr(self, '_keyword_items', [])
        if not keywords:
            self._update_keyword_nav_buttons()
            return

        page_size = self._get_keyword_page_size()
        max_start = max(0, len(keywords) - page_size)
        self._keyword_page_start = min(getattr(self, '_keyword_page_start', 0), max_start)
        current_keywords = keywords[self._keyword_page_start:self._keyword_page_start + page_size]

        for kw in current_keywords:
            is_selected = any(k.upper() == kw.upper() for k in self._keyword_selected)
            btn = tk.Button(
                self._kp_inner,
                text=kw,
                font=("SF Pro Display", 11, "bold"),
                bg=self.bg_frosted_selected if is_selected else self.bg_frosted,
                fg="#ffffff" if is_selected else self.fg_primary,
                activebackground=self.bg_frosted_hover,
                relief="flat",
                padx=5, pady=1,
                cursor="hand2",
                command=lambda k=kw: self.toggle_keyword(k)
            )
            btn.pack(side="left", padx=2, pady=2)
            self._keyword_btns[kw] = btn

        self._update_keyword_nav_buttons()

    def _on_keyword_picker_resize(self, event=None):
        """关键词区域尺寸变化后，按新宽度重新计算当前页展示内容"""
        if getattr(self, '_keyword_items', None):
            self.after_idle(self._render_keyword_picker)
        else:
            self._update_keyword_nav_buttons()

    def _shift_keyword_page(self, direction):
        """使用左右小按钮切换关键词分页，展示剩余关键词"""
        keywords = getattr(self, '_keyword_items', [])
        if not keywords:
            return

        page_size = self._get_keyword_page_size()
        max_start = max(0, len(keywords) - page_size)
        new_start = getattr(self, '_keyword_page_start', 0) + direction * page_size
        self._keyword_page_start = max(0, min(max_start, new_start))
        self._render_keyword_picker()

    def _update_keyword_nav_buttons(self):
        """根据关键词总数和当前页位置更新左右按钮可用状态"""
        if not all(hasattr(self, attr) for attr in ('_kp_left_btn', '_kp_right_btn')):
            return

        keywords = getattr(self, '_keyword_items', [])
        page_size = self._get_keyword_page_size()
        max_start = max(0, len(keywords) - page_size)
        current_start = getattr(self, '_keyword_page_start', 0)

        self._kp_left_btn.config(state="normal" if current_start > 0 else "disabled")
        self._kp_right_btn.config(state="normal" if current_start < max_start else "disabled")

    def update_keyword_picker(self, keyword_list):
        """更新关键词选择器：清除旧按钮，按分页方式展示 keyword_list"""
        if not hasattr(self, '_kp_inner'):
            return

        self._keyword_selected = set()

        seen = set()
        unique_kws = []
        for kw in keyword_list:
            kw = kw.strip()
            if len(kw) > 1 and kw.upper() not in seen:
                seen.add(kw.upper())
                unique_kws.append(kw)

        self._keyword_items = unique_kws
        self._keyword_page_start = 0
        self._render_keyword_picker()

    def toggle_keyword(self, keyword):
        """点击关键词按钮：亮起则选中，再次点击取消选中，独立于搜索栏内容"""
        kw_upper = keyword.upper()
        already_selected = any(k.upper() == kw_upper for k in self._keyword_selected)

        if already_selected:
            # 取消选中：从集合中移除，按钮变暗
            self._keyword_selected = {k for k in self._keyword_selected if k.upper() != kw_upper}
            if keyword in self._keyword_btns:
                self._keyword_btns[keyword].config(
                    bg=self.bg_frosted, fg=self.fg_primary)
        else:
            # 选中：加入集合，按钮变蓝
            self._keyword_selected.add(keyword)
            if keyword in self._keyword_btns:
                self._keyword_btns[keyword].config(
                    bg=self.bg_frosted_selected, fg="#ffffff")

        # 触发搜索（关键词选中状态与 search_var 合并）
        if self.current_view == 'price':
            self.after(80, self.search_price_list)

    def _clear_keyword_picker(self):
        """清除所有已选关键词按钮高亮（搜索栏内容保留），重新触发搜索"""
        for kw, btn in self._keyword_btns.items():
            try:
                btn.config(bg=self.bg_frosted, fg=self.fg_primary)
            except Exception:
                pass
        self._keyword_selected.clear()
        if self.current_view == 'price':
            self.after(80, self.search_price_list)

    def perform_initial_search(self, keyword):
        """执行初始搜索（用蓝色高亮）"""
        if not keyword:
            return

        # 清除之前的蓝色高亮
        self.clear_blue_highlights()

        # 检查Treeview是否存在
        if not hasattr(self, 'price_tree') or not self.price_tree.winfo_exists():
            return

        # 执行搜索
        kw = keyword.strip().upper()

        # 获取当前有效的所有项目
        try:
            current_items = list(self.price_tree.get_children())
        except:
            return

        if not current_items:
            return

        # 存储初始搜索关键词和匹配项
        self.blue_highlight_keyword = kw
        self.blue_highlight_items = []  # 重置列表

        # 查找匹配项
        matched_items = []
        for item in current_items:
            try:
                values = self.price_tree.item(item, "values")
                if values and any(kw in str(cell).upper() for cell in values):
                    matched_items.append(item)
                    # 使用蓝色高亮
                    self._set_price_item_tags(item, 'blue_highlight')
            except:
                # 如果获取item失败，跳过这个项目
                continue

        self.blue_highlight_items = matched_items

        if matched_items:
            try:
                first_match = matched_items[0]
                self.price_tree.selection_set(first_match)
                self.price_tree.see(first_match)

                index = current_items.index(first_match)
                self.price_tree.yview_moveto(max(0, (index - 2) / len(current_items)))

                # 更新状态提示
                self.update_search_stats(f"已定位到商品代码: {keyword} (蓝色高亮)", len(matched_items))
            except Exception as e:
                logging.error(f"定位到匹配项时出错: {e}")

    def clear_price_highlights(self):
        """清除价目表的所有高亮"""
        if hasattr(self, 'price_tree_items'):
            for item in self.price_tree_items:
                self._set_price_item_tags(item)   # 只保留高度标签，清除高亮
        self.initial_highlight_items = []

    def update_search_stats(self, message, match_count=0):
        """更新搜索统计信息"""
        if hasattr(self, 'result_stats_label') and self.result_stats_label.winfo_exists():
            if match_count > 0:
                self.result_stats_label.config(
                    text=f"{message} | 找到 {match_count} 个匹配项 | F3=下一个 | Shift+F3=上一个"
                )
            else:
                self.result_stats_label.config(text=message)


# -------------------- 全局搜索接口 --------------------
# 存储主窗口实例的全局变量
main_app_instance = None


def global_search_from_price_tool(keyword):
    """
    从价格查询工具调用的全局搜索接口
    """
    global main_app_instance

    # 简化这部分代码
    if main_app_instance is None or not main_app_instance.winfo_exists():
        main_app_instance = SeaStarApp()

    # 显示已经存在的实例
    main_app_instance.show_window()

    # 直接显示全局搜索界面
    main_app_instance.show_global_search()
    main_app_instance.search_var.set(keyword)
    main_app_instance.perform_global_search()


def price_list_from_price_tool(company_name, callback=None, search_keyword=None,
                                keyword_list=None, customer_code=None, customer_desc=None):
    """
    从价格查询工具调用的价目表接口
    :param company_name:   公司名称
    :param callback:       双击选择的回调函数
    :param search_keyword: 初始定位关键词（U8代码）
    :param keyword_list:   关键词列表（用于关键词选择器）
    :param customer_code:  客户商品代码（在价目表顶部显示）
    :param customer_desc:  客户商品描述（在价目表顶部显示）
    """
    global main_app_instance

    instance_valid = False
    if main_app_instance is not None:
        try:
            if main_app_instance.winfo_exists():
                instance_valid = True
        except Exception as e:
            logging.error(f"检查窗口实例状态失败: {e}")
            main_app_instance = None

    if not instance_valid:
        main_app_instance = SeaStarApp()

    main_app_instance.price_tree_select_callback = callback if callback else None
    main_app_instance.show_window()
    main_app_instance.show_price_list_from_external(
        company_name, search_keyword,
        keyword_list=keyword_list,
        customer_code=customer_code,
        customer_desc=customer_desc
    )

    return main_app_instance


# -------------------- main --------------------
if __name__ == "__main__":
    try:
        # 检查数据库是否存在（使用 get_db_path() 统一路径解析）
        if not os.path.exists(get_db_path()):
            logging.warning(f"数据库文件不存在: {get_db_path()}")

        from price_query_system import PriceQueryTool

        root = tk.Tk()
        app = PriceQueryTool(root)
        root.mainloop()

    except Exception as e:
        logging.error(f"程序启动失败: {e}")
        logging.error(traceback.format_exc())