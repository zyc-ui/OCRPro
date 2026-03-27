# config.py
"""
单一数据源：所有模块共享的列定义、路径、宽度配置。
修改此文件即可同步到 price_query_system.py 和 main.py。
"""

import sys as _sys
import os as _os


# ── 数据库路径（打包 / 开发双模式） ──────────────────────────────────────────
def get_db_path() -> str:
    """
    返回 SQLite 数据库的绝对路径，兼容 PyInstaller onedir 打包模式。

    路径解析优先级：
      1. exe 同级目录下的 database_data.db
         （便于运维人员不重新打包直接替换数据库文件）
      2. _internal/database_data.db
         （PyInstaller onedir 默认打包位置）
      3. 当前工作目录的 database_data.db
         （开发模式兜底）
    """
    if getattr(_sys, 'frozen', False):
        exe_dir = _os.path.dirname(_sys.executable)

        # 优先：exe 同级（热更新场景）
        beside_exe = _os.path.join(exe_dir, 'database_data.db')
        if _os.path.isfile(beside_exe):
            return beside_exe

        # 其次：_internal 内（打包默认位置）
        return _os.path.join(exe_dir, '_internal', 'database_data.db')

    # 开发模式
    return 'database_data.db'


# ── FullList 列定义（顺序与 SQLite 列顺序严格对应，索引 0-33） ───────────────
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
    "PACKING_DIMENSION_L_x_W_x_H",                      # 16
    "PACKING_WEIGHT_KG",                                 # 17
    "HS_Code",                                           # 18
    "COO",                                               # 19
    "DATE",                                              # 20
    "UNIT",                                              # 21
    "Cost_Price",                                        # 22  ← PRICE_COL_START
    "High_Price",                                        # 23
    "Medium_Price",                                      # 24
    "L\nGROUP_3",                                       # 25
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
    "SSM 7SEA",         # 27  （数据库列保留，仅从下拉选项移除）
    "Seven Seas",       # 28
    "Wrist Far East",   # 29
    "Anchor Marine",    # 30
    "RMS Marine",       # 31
    "Fuji Trading",     # 32
    "Con Lash",         # 33
]

assert len(FL_DB_COLS) == len(FL_DISPLAY), (
    f"列定义不匹配：FL_DB_COLS={len(FL_DB_COLS)} 列，FL_DISPLAY={len(FL_DISPLAY)} 列"
)

# ── 区间常量 ────────────────────────────────────────────────────────────────
PRICE_COL_START_IDX   = 22
L_GROUP_3_IDX         = 25
COMPANY_COL_START_IDX = 26

BASE_INFO_INDICES: list[int] = list(range(PRICE_COL_START_IDX))
GENERIC_PRICE_INDICES: list[int] = list(range(PRICE_COL_START_IDX, L_GROUP_3_IDX))

# ── 公司映射（显示名 → FL_DISPLAY 索引）── SSM 7SEA 已从下拉选项移除 ──────────
FL_COMPANY_DISPLAY_TO_IDX: dict[str, int] = {
    "SINWA SGP":      26,
    # "SSM 7SEA": 27,   ← 已移除（与 Seven Seas 重复）
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
    "SINWA SGP": 110,    "Seven Seas": 110,
    "Wrist Far East": 110, "Anchor Marine": 110, "RMS Marine": 110,
    "Fuji Trading": 110, "Con Lash": 110, "IMAGE_DATA": 120,
}