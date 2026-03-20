# config.py
"""
单一数据源：所有模块共享的列定义、路径、宽度配置。
修改此文件即可同步到 price_query_system.py 和 main.py。
"""

import sys as _sys
import os as _os


# ── 数据库路径（打包 / 开发双模式） ──────────────────────────────────────────
def get_db_path() -> str:
    """返回 SQLite 数据库的绝对路径，兼容 PyInstaller onedir 打包模式。"""
    if getattr(_sys, 'frozen', False):
        return _os.path.join(
            _os.path.dirname(_sys.executable),
            '_internal', 'database_data.db'
        )
    return 'database_data.db'


# ── FullList 列定义（顺序与 SQLite 列顺序严格对应，索引 0-33） ───────────────
# 注意：FL_DB_COLS[i] 与 FL_DISPLAY[i] 必须一一对应。
# 启动时的 assert 可在 CI / 调试时立即暴露不匹配。
FL_DB_COLS: list[str] = [
    "Brand_Sort",                                        # 0
    "NO_",                                               # 1
    "SEASTAR_U8_CODE",                                   # 2
    "IMPA",                                              # 3
    "KERGER_IMATECH",                                    # 4
    "DESCRIPTION",                                       # 5
    "DETAILS",                                           # 6
    "OFFER",                                             # 7
    "REMARK1",                                           # 8
    "REMARK2",                                           # 9
    "Quantity",                                          # 10
    "BATTERY___INPUT_TYPE",                              # 11
    "IP_Rating",                                         # 12
    "TEMP__CLASS_GAS",                                   # 13
    "SURFACE_TEMP_DUST",                                 # 14
    "CERT",                                              # 15
    "PACKING_DIMENSION_L_x_W_x_H",                      # 16  ← 移除换行符，与实际Excel列对齐
    "PACKING_WEIGHT_KG",                                 # 17
    "HS_Code",                                           # 18
    "COO",                                               # 19
    "DATE",                                              # 20
    "UNIT",                                              # 21
    "Cost_Price",                                        # 22  ← PRICE_COL_START
    "High_Price",                                        # 23
    "Medium_Price",                                      # 24
    "L\nGROUP_3",                                       # 25  ← 若Excel表头有换行则保留，否则改为 "L_GROUP_3"
    "SINWA_SINGAPORE_PTE_LTD",                          # 26  ← COMPANY_COL_START
    "SSM_\n7SEA",                                       # 27
    "Seven_Seas_Maritime_Services_Singapore_Pte_Ltd",   # 28
    "Wrist_Far_East_Singapore_Pte_Ltd",                 # 29
    "Anchor_Marine_Supplies_Pte_Ltd",                   # 30
    "RMS_Marine_&_Offshore_Service_Pte_Ltd",            # 31
    "Fuji_Trading_S_Pte_Ltd",                           # 32
    "Con_Lash_Supplies_Pte_Ltd",                        # 33
]

FL_DISPLAY: list[str] = [
    "Brand Sort",        # 0
    "NO",                # 1
    "U8代码",            # 2
    "IMPA代码",          # 3
    "KERGER/IMATECH",   # 4
    "描述",              # 5
    "详情",              # 6
    "报价",              # 7
    "备注1",             # 8
    "备注2",             # 9
    "库存量",            # 10
    "Battery/Input",    # 11
    "IP Rating",        # 12
    "Temp Class Gas",   # 13
    "Surface Temp Dust",# 14
    "CERT",             # 15
    "Packing Dim",      # 16
    "Packing Weight(KG)",# 17
    "HS Code",          # 18
    "COO",              # 19
    "DATE",             # 20
    "单位",             # 21
    "Cost Price",       # 22  ← PRICE_COL_START_IDX
    "High Price",       # 23
    "Medium Price",     # 24
    "L GROUP 3",        # 25
    "SINWA SGP",        # 26  ← COMPANY_COL_START_IDX
    "SSM 7SEA",         # 27
    "Seven Seas",       # 28
    "Wrist Far East",   # 29
    "Anchor Marine",    # 30
    "RMS Marine",       # 31
    "Fuji Trading",     # 32
    "Con Lash",         # 33
]

# 在模块加载时立即校验，防止两个列表因手误长度不一致悄悄出错
assert len(FL_DB_COLS) == len(FL_DISPLAY), (
    f"列定义不匹配：FL_DB_COLS={len(FL_DB_COLS)} 列，FL_DISPLAY={len(FL_DISPLAY)} 列"
)

# ── 区间常量 ────────────────────────────────────────────────────────────────
PRICE_COL_START_IDX   = 22   # Cost_Price 起始索引（含）
L_GROUP_3_IDX         = 25   # L GROUP 3 独立索引
COMPANY_COL_START_IDX = 26   # 第一家公司列（SINWA）的起始索引

# 非价格基础列（信息列）：0-21，可被用户切换显示
BASE_INFO_INDICES: list[int] = list(range(PRICE_COL_START_IDX))          # [0..21]
# 通用价格列（无特定公司时显示）：Cost/High/Medium Price
GENERIC_PRICE_INDICES: list[int] = list(range(PRICE_COL_START_IDX, L_GROUP_3_IDX))  # [22,23,24]

# ── 公司映射（显示名 → FL_DISPLAY 索引） ────────────────────────────────────
FL_COMPANY_DISPLAY_TO_IDX: dict[str, int] = {
    "SINWA SGP":      26,
    "SSM 7SEA":       27,
    "Seven Seas":     28,
    "Wrist Far East": 29,
    "Anchor Marine":  30,
    "RMS Marine":     31,
    "Fuji Trading":   32,
    "Con Lash":       33,
}

# 公司下拉选项（UI 用）
COMPANY_OPTIONS: list[str] = ["Other"] + list(FL_COMPANY_DISPLAY_TO_IDX.keys())

# ── 列宽配置 ────────────────────────────────────────────────────────────────
FL_COL_WIDTHS: dict[str, int] = {
    "Brand Sort": 90,    "NO": 60,           "U8代码": 140,      "IMPA代码": 110,
    "KERGER/IMATECH": 110, "描述": 280,      "详情": 220,        "报价": 180,
    "备注1": 140,        "备注2": 140,       "库存量": 70,
    "Battery/Input": 110, "IP Rating": 75,  "Temp Class Gas": 100,
    "Surface Temp Dust": 115, "CERT": 90,   "Packing Dim": 130,
    "Packing Weight(KG)": 115, "HS Code": 90, "COO": 55,        "DATE": 80,
    "单位": 55,
    "Cost Price": 95,    "High Price": 95,   "Medium Price": 95,
    "L GROUP 3": 90,
    "SINWA SGP": 110,    "SSM 7SEA": 110,    "Seven Seas": 110,
    "Wrist Far East": 110, "Anchor Marine": 110, "RMS Marine": 110,
    "Fuji Trading": 110, "Con Lash": 110,
}