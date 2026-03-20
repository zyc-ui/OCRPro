# translate.py
# ─────────────────────────────────────────────────────────────────────────────
# 前端 UI 翻译模块（仅翻译显示文字，后端字段/数据库列名不受影响）
#
# 使用方式：
#   from translate import t, set_lang, get_lang
#   t("公司代码")          → 中文模式返回 "公司代码"，英文模式返回 "Company"
#   set_lang("en")         → 切换到英文
#   set_lang("zh")         → 切换回中文
# ─────────────────────────────────────────────────────────────────────────────

_lang: str = "zh"   # 全局语言，默认中文


# ══════════════════════════════════════════════════════════════════════════════
# 翻译字典：中文原文 → 英文译文
# 注意：英文译文尽量贴近海事/船供行业惯用表达
# ══════════════════════════════════════════════════════════════════════════════
TRANSLATIONS: dict[str, str] = {

    # ── 顶部控制栏 ────────────────────────────────────────────────────────────
    "公司代码":                         "Company",
    "OCR识别":                          "OCR Scan",
    "追加识别":                         "Append Scan",
    "查询价格":                         "Query Price",
    "复制表格":                         "Copy Table",
    "清空":                             "Clear",

    # ── 语言切换按钮本身 ──────────────────────────────────────────────────────
    # 当前显示 "EN" 表示"点我切英文"；切过去后显示 "中文" 表示"点我切回来"
    "EN":                               "中文",

    # ── 商品代码提示栏 ────────────────────────────────────────────────────────
    "商品代码":                         "Item Code",
    "未识别到商品代码":                  "No item code recognized",

    # ── 列显示控制区 ──────────────────────────────────────────────────────────
    "显示列:":                          "Columns:",

    # ── Treeview 固定列 ───────────────────────────────────────────────────────
    "行号":                             "No.",
    "客户描述":                         "Customer Desc",
    "数量":                             "Qty",
    # "Item NO."  保持不变（已是英文）
    # "UOM"       保持不变

    # ── FL_DISPLAY 中的中文列名 ───────────────────────────────────────────────
    "U8代码":                           "U8 Code",
    "IMPA代码":                         "IMPA Code",
    "描述":                             "Description",
    "详情":                             "Details",
    "报价":                             "Offer / Quote",
    "备注1":                            "Remark 1",
    "备注2":                            "Remark 2",
    "库存量":                           "Stock Qty",
    "单位":                             "Unit",
    # 以下已是英文，无需翻译：
    # Brand Sort, NO, KERGER/IMATECH, Battery/Input, IP Rating,
    # Temp Class Gas, Surface Temp Dust, CERT, Packing Dim,
    # Packing Weight(KG), HS Code, COO, DATE,
    # Cost Price, High Price, Medium Price,
    # L GROUP 3, SINWA SGP, SSM 7SEA, Seven Seas,
    # Wrist Far East, Anchor Marine, RMS Marine, Fuji Trading, Con Lash

    # ── 编辑窗口 ──────────────────────────────────────────────────────────────
    "编辑商品代码 / 客户描述 / 数量":    "Edit Item / Description / Qty",
    "商品代码:":                        "Customer IMPA:",
    "客户描述:":                        "Customer Desc:",
    "数量:":                            "Qty:",
    "确定":                             "OK",
    "识别":                             "Lookup",
    "取消":                             "Cancel",

    # ── 导出对话框 ────────────────────────────────────────────────────────────
    "导出报价表格":                      "Export Quotation",
    "选择导出方式：":                    "Select export format:",
    "复制表格\n在邮件粘贴即可":          "Copy Table\n(paste into email)",
    "导出邮件\n双击可用邮件客户端打开":  "Export .eml\n(open with mail client)",
    "复制纯文本":                        "Copy as Plain Text",

    # ── 消息框标题 ────────────────────────────────────────────────────────────
    "警告":                             "Warning",
    "错误":                             "Error",
    "完成":                             "Done",
    "成功":                             "Success",
    "提示":                             "Info",
    "确认删除":                         "Confirm Delete",

    # ── 消息框正文 ────────────────────────────────────────────────────────────
    "请先选择公司":                      "Please select a company first",
    "请先识别商品代码":                  "Please scan item codes first",
    "请先选择要删除的行":                "Please select a row to delete",
    "确定要删除选中的行吗？":            "Delete the selected row?",
    "没有数据可复制":                    "No data to copy",
    "数据已复制到剪贴板":               "Data copied to clipboard",
    "纯文本表格已复制到剪贴板":         "Plain text table copied to clipboard",
    "商品代码为空，无法重新识别":        "Item code is empty, cannot re-query",
    "请先选择公司后再识别":             "Please select a company before re-querying",
    "未找到匹配商品":                    "No matching item found",
    "无法创建数据库连接":               "Cannot create database connection",

    # ── 状态标签（codes_label 动态前缀） ─────────────────────────────────────
    "已识别到商品:":                    "Items recognized:",
    "追加识别到商品:":                  "Items appended:",
    "已选择公司:":                      "Company selected:",
    "价格列:":                          "Price col:",
    "High Price / Medium Price":        "High Price / Medium Price",   # 保持不变

    # ── 行高控制区（main.py 价目表窗口，供 SeaStarApp 使用） ─────────────────
    "搜索":                             "Search",
    "搜索:":                            "Search:",
    "全局搜索:":                        "Global Search:",
    # ── main.py 价目表控制区按钮 ─────────────────────────────────────────────
    "行高":                             "Row Ht",
    "✕清除":                           "✕Clear",
    "✕关键词":                         "✕Keywords",
    "📍定位":                          "📍Locate",
    "行":                              "rows",      # 行高数字后缀
}


# ══════════════════════════════════════════════════════════════════════════════
# 公开 API
# ══════════════════════════════════════════════════════════════════════════════

def set_lang(lang: str) -> None:
    """设置全局语言。lang = 'zh'（中文）或 'en'（英文）。"""
    global _lang
    _lang = lang if lang in ("zh", "en") else "zh"


def get_lang() -> str:
    """返回当前语言代码。"""
    return _lang


def t(text: str) -> str:
    """
    翻译函数。
    - 中文模式：原样返回 text（零开销）。
    - 英文模式：在 TRANSLATIONS 中查找，未找到则原样返回。
    """
    if _lang == "zh":
        return text
    return TRANSLATIONS.get(text, text)


def is_en() -> bool:
    """当前是否为英文模式。"""
    return _lang == "en"