"""
category_router.py — 类目路由器

职责：
  1. 从客户描述中识别产品大类（CATEGORY）
  2. 从价目表行集合中过滤出同类候选行
  3. 供 matcher.py 的两阶段检索使用

设计原则：
  - 纯规则 + 正则，零外部依赖，离线可用
  - 关键词按"区分度高 → 低"排列，先匹配先得
  - 每个类目附带"反向排除词"，防止误归类
  - 未命中任何类目时返回全量（保守退化）

类目层级：
  LIGHTING          照明 / 灯具
  CABLE_CONNECTOR   电缆 / 端子 / 接头
  BATTERY           蓄电池 / 干电池
  SAFETY            安全 / 救生 / 消防
  MECHANICAL        机械 / 泵 / 阀 / 轴承
  FILTER            过滤器 / 滤芯
  INSTRUMENT        仪表 / 传感器 / 测量
  ELECTRICAL        电气 / 开关 / 熔断器 / 继电器
  PAINT_CHEMICAL    油漆 / 化学品 / 清洗剂
  ROPE_MOORING      绳索 / 缆绳 / 系泊
  HVAC              空调 / 通风 / 制冷
  FASTENER          紧固件 / 螺栓 / 螺母
  PIPE_FITTING      管道 / 接头 / 法兰
  HOSE              软管 / 胶管
  GASKET_SEAL       密封件 / 垫片 / O型圈
  LUBRICANT         润滑 / 油脂 / 机油
  TOOL              工具 / 设备
  PPE               个人防护
  GENERAL           (未命中，退化至全量)
"""

import logging
import re
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 类目定义表
# 格式：每条为 (category_id, include_patterns, exclude_patterns)
#   include_patterns : list[str]  — 正则片段，任一命中即归入本类
#   exclude_patterns : list[str]  — 正则片段，命中则否决本类归入
#
# 排列顺序即优先级（先匹配先胜出），请将区分度高的规则放前面
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_RULES: List[Tuple[str, List[str], List[str]]] = [

    # ── 照明 ──────────────────────────────────────────────────────────────
    ("LIGHTING", [
        r"\bla?mp\b", r"\blamps\b",
        r"\bfluorescent\b", r"\bfluor\b",
        r"\bincandescent\b",
        r"\bled\b(?!.*battery)",          # LED 但不含 battery
        r"\bbulb\b", r"\bglobe\b",
        r"\bluminaire\b", r"\blight(ing)?\b",
        r"\bnavigation\s+light\b",
        r"\bsearchlight\b", r"\bfloodlight\b",
        r"\b(4[0-9]{3}k|[0-9]+[kK]\s*color)\b",  # 色温如 4100K
        r"\blumen\b", r"\bcct\b",
        r"\b(e27|e14|e40|b22|g13|g23|gu10)\b",    # 灯头型号
    ], [
        r"\bbattery\b", r"\bcharger\b",
    ]),

    # ── 蓄电池 / 干电池 ───────────────────────────────────────────────────
    ("BATTERY", [
        r"\bbattery\b", r"\bbatteries\b",
        r"\baccumulator\b",
        r"\b(ni-?mh|ni-?cd|li-?ion|agm|vrla|gel)\b",
        r"\b(12v|24v|6v)\s*\d+\s*ah\b",
        r"\blead.?acid\b",
        r"\bups\b",
    ], []),

    # ── 电缆 / 端子 / 接头 ─────────────────────────────────────────────────
    ("CABLE_CONNECTOR", [
        r"\bcable\b", r"\bwire\b",
        r"\bcrimping\b", r"\bcrimp\b",
        r"\bterminal\b", r"\bconnector\b",
        r"\bcable\s+shoe\b", r"\bshoe\b(?=.*\btype\b|\bnominal\b)",
        r"\blug\b", r"\bgland\b",
        r"\bsleeve\b(?=.*\bcable|connect)",
        r"\bawg\b", r"\bmm2\b",
        r"\b(r-tg|rg-|nh-|sv-|fv-|dv-)\w*\b",   # 端子型号前缀
        r"\brnb\b|\brnb\d",
        r"\bjunction\s*box\b",
    ], []),

    # ── 安全 / 救生 / 消防 ─────────────────────────────────────────────────
    ("SAFETY", [
        r"\blife\s*(jacket|buoy|raft|ring|boat)\b",
        r"\bfire\s*(extinguish|alarm|detector|hose|blanket|suit)\b",
        r"\bimmersion\s*suit\b",
        r"\bsafety\s*(line|harness|net|helmet|goggle|boot)\b",
        r"\bmuster\b", r"\bevacuation\b",
        r"\brescue\b",
        r"\bepirb\b", r"\bsart\b",
        r"\bsmoke\s*detector\b",
        r"\bco2?\s*alarm\b",
        r"\bparachute\s*flare\b",
        r"\bfireproof\b", r"\bfire.?proof\b",
        r"\bpyrotechnic\b",
    ], []),

    # ── 仪表 / 传感器 / 测量 ───────────────────────────────────────────────
    ("INSTRUMENT", [
        r"\b(pressure|temperature|flow|level|speed)\s*(gauge|sensor|transmitter|switch|indicator)\b",
        r"\bgauge\b", r"\btransducer\b", r"\btransmitter\b",
        r"\bthermometer\b", r"\bthermocoupl\b",
        r"\bmanometer\b", r"\bbarometer\b",
        r"\banemometer\b",
        r"\bultrasonic\b",
        r"\bflowmeter\b",
        r"\binclinometer\b",
        r"\bechometer\b", r"\bsonar\b",
        r"\bmultimeter\b", r"\bvoltmeter\b", r"\bammeter\b",
        r"\bdetector\b",
    ], [r"\bfire\b", r"\bsmoke\b"]),   # 排除安全类 detector

    # ── 过滤器 / 滤芯 ───────────────────────────────────────────────────────
    ("FILTER", [
        r"\bfilter\b", r"\bfiltrat\b",
        r"\bstrainer\b",
        r"\bcartridge\b",
        r"\bfilter\s*element\b",
        r"\bseparator\b",
        r"\bpurifier\b",
        r"\bde-?aerator\b",
    ], []),

    # ── 机械 / 泵 / 阀 / 轴承 ─────────────────────────────────────────────
    ("MECHANICAL", [
        r"\bpump\b", r"\bimpeller\b",
        r"\bvalve\b", r"\bcock\b",
        r"\bbearing\b",
        r"\bgasket\b(?!.*o.?ring)",       # 垫片（非O型圈）
        r"\bshaft\b", r"\bgear\b",
        r"\bcoupling\b", r"\bflanges?\b",
        r"\bpiston\b", r"\bcylinder\b",
        r"\bcompressor\b", r"\bturbine\b",
        r"\bwinch\b", r"\bmooring\s*equipment\b",
        r"\banchor\b",
    ], []),

    # ── 电气 / 开关 / 熔断器 / 继电器 ────────────────────────────────────
    ("ELECTRICAL", [
        r"\bswitch\b", r"\bbreaker\b", r"\bcircuit.?breaker\b",
        r"\bfuse\b", r"\brelay\b",
        r"\btransformer\b",
        r"\binverter\b", r"\bconverter\b", r"\bcharger\b",
        r"\bcontactor\b", r"\bstarter\b",
        r"\bpanel\b", r"\bdistribution.?board\b",
        r"\bsocket\b", r"\bplug\b",
        r"\bvfd\b", r"\bvariable\s*freq\b",
        r"\benclosure\b",
    ], [r"\bbattery\b"]),

    # ── 管道 / 接头 / 法兰 ─────────────────────────────────────────────────
    ("PIPE_FITTING", [
        r"\bpipe\b", r"\btubing?\b",
        r"\belbow\b", r"\btee\b(?!\s*shirt)",
        r"\breducer\b",
        r"\bnipple\b",
        r"\bflange\b",
        r"\bunion\b",
        r"\bfitting\b",
        r"\bmanifold\b",
        r"\bcheck\s*valve\b",
        r"\bball\s*valve\b",
        r"\bangle\s*valve\b",
    ], []),

    # ── 软管 ────────────────────────────────────────────────────────────────
    ("HOSE", [
        r"\bhose\b",
        r"\bflexible\s*pipe\b",
        r"\brubber\s*hose\b",
        r"\bfire\s*hose\b",
    ], []),

    # ── 密封件 / 垫片 / O型圈 ─────────────────────────────────────────────
    ("GASKET_SEAL", [
        r"\bo.?ring\b",
        r"\bseal\b", r"\bsealing\b",
        r"\bgasket\b",
        r"\bpacking\b",
        r"\bmechanical\s*seal\b",
        r"\blip\s*seal\b",
    ], [r"\bsafety\b"]),

    # ── 绳索 / 系泊 ─────────────────────────────────────────────────────────
    ("ROPE_MOORING", [
        r"\brope\b", r"\bline\b(?=.*\b(mooring|nylon|polyester|wire)\b)",
        r"\bmooring\b",
        r"\bwire\s*rope\b",
        r"\bfibre\s*rope\b",
        r"\bpolyester\b",
        r"\bnylon\b(?=.*\brope|line\b)",
        r"\bchain\b",
        r"\bshackle\b",
        r"\bbollard\b",
    ], []),

    # ── 空调 / 通风 / 制冷 ─────────────────────────────────────────────────
    ("HVAC", [
        r"\bair.?condition\b", r"\bac\b(?=.*\bunit\b)",
        r"\brefrigerat\b",
        r"\bventilat\b", r"\bfan\b", r"\bblower\b",
        r"\bduct\b", r"\bdiffuser\b",
        r"\bevaporat\b", r"\bcondenser\b",
        r"\bfreon\b", r"\brefrigerant\b",
        r"\bchiller\b",
    ], []),

    # ── 润滑 / 油脂 ────────────────────────────────────────────────────────
    ("LUBRICANT", [
        r"\bgreaser?\b", r"\blubricat\b",
        r"\bengine\s*oil\b", r"\bgear\s*oil\b",
        r"\bhydraulic\s*oil\b",
        r"\banti.?freeze\b",
        r"\bcoolant\b",
    ], []),

    # ── 油漆 / 化学品 ──────────────────────────────────────────────────────
    ("PAINT_CHEMICAL", [
        r"\bpaint\b", r"\bprimer\b", r"\bcoating\b",
        r"\bantifoul\b",
        r"\bsolvent\b", r"\bclean(er|ing)\b",
        r"\bchemical\b",
        r"\bdetergent\b", r"\bdegrease\b",
    ], []),

    # ── 紧固件 ────────────────────────────────────────────────────────────
    ("FASTENER", [
        r"\bbolt\b", r"\bnut\b", r"\bscrew\b",
        r"\bwasher\b", r"\bstud\b",
        r"\banchor\s*bolt\b",
        r"\brivet\b",
        r"\bthread\b",
    ], []),

    # ── 工具 ───────────────────────────────────────────────────────────────
    ("TOOL", [
        r"\bwrench\b", r"\bspanner\b",
        r"\bscrewdriver\b",
        r"\bpliers?\b",
        r"\bhammer\b",
        r"\bdrill\b",
        r"\bsaw\b",
        r"\btorque\s*wrench\b",
        r"\bmegger\b",
    ], []),

    # ── 个人防护 (PPE) ─────────────────────────────────────────────────────
    ("PPE", [
        r"\bhelmet\b", r"\bhard\s*hat\b",
        r"\bgloves?\b",
        r"\bgoggles?\b", r"\beye.?protect\b",
        r"\bear.?protect\b", r"\bear\s*plug\b",
        r"\brespirator\b", r"\bfacemask\b",
        r"\boverall\b", r"\bboilersuit\b",
        r"\bsafety\s*(boots?|shoes?)\b",
    ], []),
]


# ─────────────────────────────────────────────────────────────────────────────
# 预编译正则（模块加载时执行一次）
# ─────────────────────────────────────────────────────────────────────────────

_COMPILED_RULES: List[Tuple[str, List[re.Pattern], List[re.Pattern]]] = [
    (
        cat,
        [re.compile(p, re.IGNORECASE) for p in includes],
        [re.compile(p, re.IGNORECASE) for p in excludes],
    )
    for cat, includes, excludes in _CATEGORY_RULES
]


# ─────────────────────────────────────────────────────────────────────────────
# 类目归属字段（价目表行里用来判断所属类目的列）
# 优先级从高到低，列名对应 FL_DISPLAY
# ─────────────────────────────────────────────────────────────────────────────
_CATEGORY_SOURCE_COLS = ["描述", "详情", "报价", "备注1", "备注2"]


# ─────────────────────────────────────────────────────────────────────────────
# 公开函数
# ─────────────────────────────────────────────────────────────────────────────

def classify_query(text: str) -> str:
    """
    将客户描述文本归入一个大类，返回类目 ID 字符串。
    无法命中时返回 "GENERAL"。

    >>> classify_query("LED GLOBE LAMP 85-265VAC 12W 4100K")
    'LIGHTING'
    >>> classify_query("CABLE SHOE CLAMPING TYPE R-TG NOMINAL SIZE 5.5-4")
    'CABLE_CONNECTOR'
    >>> classify_query("12V 100AH AGM BATTERY")
    'BATTERY'
    """
    if not text or not text.strip():
        return "GENERAL"

    t = text.strip()
    for cat, inc_pats, exc_pats in _COMPILED_RULES:
        # 先检查排除词
        if any(p.search(t) for p in exc_pats):
            continue
        # 检查包含词
        if any(p.search(t) for p in inc_pats):
            return cat

    return "GENERAL"


def _row_to_text(row: dict) -> str:
    """把一行价目表 dict 拼成用于类目判断的文本。"""
    parts = []
    for col in _CATEGORY_SOURCE_COLS:
        v = (row.get(col) or "").strip()
        if v:
            parts.append(v)
    return " | ".join(parts)


def filter_by_category(
    db_rows: List[dict],
    category: str,
    *,
    min_ratio: float = 0.0,
    fallback_threshold: int = 30,
) -> Tuple[List[int], bool]:
    """
    在 db_rows 中筛选出属于 category 的行。

    参数：
        db_rows            : 价目表行列表（FL_DISPLAY 字段的 dict）
        category           : classify_query() 返回的类目 ID
        min_ratio          : 最少保留比例（防止筛完后空集）
        fallback_threshold : 筛选结果少于此数时触发全量退化

    返回：
        (filtered_indices, is_fallback)
        filtered_indices : 命中行在 db_rows 中的原始索引列表
        is_fallback      : True 表示触发了全量退化
    """
    if category == "GENERAL" or not db_rows:
        return list(range(len(db_rows))), True

    # 对每行打分（含包含词数量，用于排序）
    inc_pats, exc_pats = [], []
    for cat, ipats, epats in _COMPILED_RULES:
        if cat == category:
            inc_pats = ipats
            exc_pats = epats
            break

    if not inc_pats:
        return list(range(len(db_rows))), True

    matched_indices: List[Tuple[int, int]] = []  # (原始索引, 命中数)
    for i, row in enumerate(db_rows):
        row_text = _row_to_text(row)
        if not row_text:
            continue
        # 命中任意排除词则跳过
        if any(p.search(row_text) for p in exc_pats):
            continue
        hit_count = sum(1 for p in inc_pats if p.search(row_text))
        if hit_count > 0:
            matched_indices.append((i, hit_count))

    if len(matched_indices) < fallback_threshold:
        logger.info(
            f"[Router] 类目 {category!r} 仅筛出 {len(matched_indices)} 行"
            f"（<{fallback_threshold}），退化至全量搜索"
        )
        return list(range(len(db_rows))), True

    # 按命中数降序，优先让匹配分更高的行靠前
    matched_indices.sort(key=lambda x: -x[1])
    indices = [i for i, _ in matched_indices]
    logger.info(f"[Router] 类目 {category!r} → 筛出 {len(indices)}/{len(db_rows)} 行")
    return indices, False


def route(
    query: str,
    db_rows: List[dict],
    *,
    fallback_threshold: int = 30,
) -> Tuple[str, List[dict], bool]:
    """
    一步完成：分类 → 过滤 → 返回候选子集。

    返回：
        (category, candidate_rows, is_fallback)
        category       : 检测到的类目
        candidate_rows : 过滤后的候选行子集（已重排序）
        is_fallback    : 是否退化到了全量
    """
    category = classify_query(query)
    indices, is_fallback = filter_by_category(
        db_rows, category, fallback_threshold=fallback_threshold
    )
    candidates = [db_rows[i] for i in indices]
    return category, candidates, is_fallback


# ─────────────────────────────────────────────────────────────────────────────
# 调试 / 测试入口
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        "LED GLOBE LAMP 85-265VAC, 12W, 4100K",
        "CABLE SHOE CLAMPING TYPE R-TG, NOMINAL SIZE 5.5-4",
        "12V 100AH AGM BATTERY",
        "CENTRIFUGAL PUMP MECHANICAL SEAL 65MM",
        "FIRE EXTINGUISHER CO2 5KG",
        "AIR FILTER ELEMENT CARTRIDGE",
        "BALL VALVE DN50 PN16 FLANGED",
        "ENGINE OIL 15W40 20L",
        "NYLON MOORING ROPE 32MM X 200M",
        "FLUORESCENT LAMP 36W T8 1200MM",
        "UNKNOWN PRODUCT XYZ",
    ]
    print(f"{'描述':<55} {'类目'}")
    print("-" * 75)
    for tc in test_cases:
        cat = classify_query(tc)
        print(f"{tc:<55} {cat}")