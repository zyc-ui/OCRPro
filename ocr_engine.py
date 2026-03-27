"""
ocr_engine.py — OCR 引擎
全屏选区 UI（tkinter）在独立 daemon 线程运行，不阻塞 pywebview 主线程。
OCR 核心逻辑（perform_ocr）是纯函数，无任何 UI 依赖。
"""

import logging
import os
import re
import sys
import threading
from typing import Callable, List, Tuple

import pytesseract
from PIL import ImageGrab


# ─────────────────────────────────────────────────────────────────────────────
# Tesseract 路径解析
#
# 优先级（由高到低）：
#   1. 环境变量 TESSERACT_CMD         （完整可执行文件路径）
#   2. 环境变量 TESSERACT_DIR         （目录，自动追加 tesseract.exe）
#   3. 打包模式下 _internal/Tesseract  （PyInstaller onedir 内嵌路径）
#   4. PATH 中的 tesseract             （系统已安装）
# ─────────────────────────────────────────────────────────────────────────────

def _get_tesseract_path() -> str:
    # 1) 直接指定可执行路径
    cmd_env = os.environ.get("TESSERACT_CMD", "").strip()
    if cmd_env:
        return cmd_env

    # 2) 指定目录，自动追加 tesseract.exe
    dir_env = os.environ.get("TESSERACT_DIR", "").strip()
    if dir_env:
        candidate = os.path.join(dir_env, "tesseract.exe")
        if os.path.isfile(candidate):
            return candidate
        # 目录存在但 exe 不在根层，尝试常见子路径
        candidate2 = os.path.join(dir_env, "bin", "tesseract.exe")
        if os.path.isfile(candidate2):
            return candidate2
        # 目录指定了但找不到 exe，仍返回拼接路径（check 时会报错，方便定位）
        return candidate

    # 3) 打包模式：在 _internal/Tesseract 内查找
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal")
        packed = os.path.join(base, "Tesseract", "tesseract.exe")
        if os.path.isfile(packed):
            return packed
        # 兼容旧版打包（直接在 exe 同级）
        legacy = os.path.join(os.path.dirname(sys.executable), "Tesseract", "tesseract.exe")
        if os.path.isfile(legacy):
            return legacy
        return packed   # 不存在时仍返回标准路径，check_tesseract() 会给出清晰报错

    # 4) 开发模式：依赖 PATH（系统已安装 Tesseract）
    return "tesseract"


TESSERACT_PATH = _get_tesseract_path()
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ─────────────────────────────────────────────────────────────────────────────
# OCR 核心：纯函数，无 UI 依赖
# ─────────────────────────────────────────────────────────────────────────────

_UNIT_KEYWORDS = {
    "PCS","PC","SET","SETS","EA","EACH","ROLL","ROLLS","BOX","BOXES",
    "PAIR","PAIRS","M","KG","G","L","LTR","LITRE","LITRES","LENGTH",
    "LOT","LOTS","NOS","NO","UNIT","UNITS","PKT","PKG","PACK","PACKS",
    "BAG","BAGS","CAN","CANS","BTL","BOTTLE","MTR","MM","CM","FT","INCH",
    "TIN","TINS","TUBE","TUBES","SHEET","SHEETS","COIL","COILS",
}

_CODE_PATTERN = r"\b(79\d{4}|33\d{4}|37\d{4})\b"


def _extract_qty_unit(txt: str) -> Tuple[str, str, str]:
    """从文本末尾提取 (clean_desc, qty, unit)。"""
    txt = txt.strip()
    if not txt:
        return "", "", ""
    # 模式1: "数量 单位"
    m = re.search(r"(\d+[.,]\d+|\d{1,5})\s+([A-Za-z]{1,8})\s*$", txt)
    if m and m.group(2).upper() in _UNIT_KEYWORDS:
        desc = txt[: m.start()].strip()
        if desc:
            return desc, m.group(1), m.group(2).upper()
    # 模式2: "数量[单位]"（紧贴）
    m = re.search(r"(\d+[.,]\d+|\d{1,5})([A-Za-z]{1,8})?\s*$", txt)
    if m:
        qty  = m.group(1)
        unit = (m.group(2) or "").upper()
        if unit not in _UNIT_KEYWORDS:
            unit = ""
        desc = txt[: m.start()].strip()
        if desc:
            return desc, qty, unit
    # 模式3: "单位 数量"
    m = re.search(r"([A-Za-z]{1,8})\s+(\d+[.,]\d+|\d{1,5})\s*$", txt)
    if m and m.group(1).upper() in _UNIT_KEYWORDS:
        desc = txt[: m.start()].strip()
        if desc:
            return desc, m.group(2), m.group(1).upper()
    # 兜底：只提取数量
    m = re.search(r"(\d+[.,]\d+|\d{1,5})\s*$", txt)
    if m:
        desc = txt[: m.start()].strip()
        if desc:
            return desc, m.group(1), ""
    return txt, "", ""


def _extract_item_no(line: str) -> Tuple[str, str]:
    line = line.strip()
    m = re.match(r"^(\d{1,4}(?:[.,]\d+)?)[.\s)\-]+(.+)$", line)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r"^(\d{1,4}(?:[.,]\d+)?)$", line)
    if m:
        return m.group(1), ""
    return "", line


def _is_qty_line(line: str) -> bool:
    return bool(re.match(r"^\d+([.,]\d+)?\s*$", line.strip()))


def perform_ocr(left: int, top: int, right: int, bottom: int) -> List[Tuple]:
    """
    执行截图 + OCR，返回 [(item_no, code, desc, qty, unit), ...]。
    纯函数，可独立测试。
    """
    screenshot = (
        ImageGrab.grab(bbox=(left, top, right, bottom))
        .convert("L")
        .point(lambda x: 0 if x < 128 else 255, "1")
    )
    text  = pytesseract.image_to_string(screenshot, lang="eng+chi_sim")
    text  = "\n".join(line.strip() for line in text.splitlines())
    logging.debug(f"[OCR] 原始文本:\n{text}")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    seen_codes: set      = set()
    all_codes:  List[str] = []
    same_descs: List[str] = []
    pure_lines: List[str] = []

    for line in lines:
        m = re.search(_CODE_PATTERN, line)
        if m:
            code = m.group(0)
            if code not in seen_codes:
                seen_codes.add(code)
                all_codes.append(code)
                same_descs.append(line[m.end():].strip())
        else:
            pure_lines.append(line)

    real_desc = [l for l in pure_lines if not _is_qty_line(l)]
    col_qty   = [l for l in pure_lines if _is_qty_line(l)]
    items: List[Tuple] = []

    def _get_qty(inline: str, idx: int) -> str:
        return inline if inline else (col_qty[idx] if idx < len(col_qty) else "")

    def _find_item_no(code: str) -> str:
        for i, raw in enumerate(lines):
            if code not in raw:
                continue
            no, _ = _extract_item_no(raw)
            if no:
                return no
            for off in range(1, 3):
                if i - off < 0:
                    break
                prev = lines[i - off].strip()
                no2, rest = _extract_item_no(prev)
                if no2 and not rest:
                    return no2
                ml = re.match(
                    r"[Ii]tem\s*[Nn][Oo]\.?\s*[:\-]?\s*(\d{1,4}(?:[.,]\d+)?)", prev
                )
                if ml:
                    return ml.group(1)
                if len(prev) > 8:
                    break
        return ""

    if not all_codes:
        for i, line in enumerate(real_desc):
            _, rest = _extract_item_no(line)
            dc, iq, iu = _extract_qty_unit(rest)
            if dc:
                items.append(("", "", dc, _get_qty(iq, i), iu))
        return items

    has_same_desc = any(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", d) for d in same_descs)

    if not has_same_desc and len(real_desc) == len(all_codes):
        for i, (code, desc) in enumerate(zip(all_codes, real_desc)):
            desc = re.sub(r"\s+", " ", desc).strip()
            dc, iq, iu = _extract_qty_unit(desc)
            items.append((_find_item_no(code), code, dc, _get_qty(iq, i), iu))
    elif has_same_desc:
        for i, (code, desc) in enumerate(zip(all_codes, same_descs)):
            desc = re.sub(r"\s+", " ", desc).strip()
            dc, iq, iu = _extract_qty_unit(desc)
            if not iq and i < len(col_qty):
                iq = col_qty[i]
            items.append((_find_item_no(code), code, dc, iq, iu))
    elif real_desc:
        desc_iter = iter(real_desc)
        for i, (code, sd) in enumerate(zip(all_codes, same_descs)):
            d = re.sub(r"\s+", " ", sd if sd.strip() else next(desc_iter, "")).strip()
            dc, iq, iu = _extract_qty_unit(d)
            items.append((_find_item_no(code), code, dc, _get_qty(iq, i), iu))
    else:
        for i, code in enumerate(all_codes):
            items.append((_find_item_no(code), code, "", _get_qty("", i), ""))

    logging.debug(f"[OCR] 最终配对: {items}")
    return items


# ─────────────────────────────────────────────────────────────────────────────
# OCREngine：带 tkinter 选区 UI 的封装
# ─────────────────────────────────────────────────────────────────────────────

class OCREngine:
    """
    负责启动全屏选区窗口并返回 OCR 结果。
    整个 tkinter 生命周期（Tk() → mainloop()）都在 daemon 线程中，
    不占用 pywebview 主线程。
    """

    def check_tesseract(self) -> bool:
        try:
            path = pytesseract.pytesseract.tesseract_cmd
            # "tesseract" 代表依赖 PATH，不检查文件存在性，直接调版本
            if path != "tesseract" and not os.path.isfile(path):
                logging.error(
                    f"[OCR] Tesseract 可执行文件不存在: {path}\n"
                    "      请设置环境变量 TESSERACT_CMD 或 TESSERACT_DIR 指向正确路径。"
                )
                return False
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logging.error(f"[OCR] Tesseract 检查失败: {e}")
            return False

    def start_selection(self, on_result: Callable[[List[Tuple]], None]) -> bool:
        """
        启动选区。OCR 完成后调用 on_result(items)。
        返回 False 表示 Tesseract 未找到。
        """
        if not self.check_tesseract():
            logging.error(f"[OCR] Tesseract 路径: {TESSERACT_PATH}")
            return False
        threading.Thread(target=self._run_ui, args=(on_result,), daemon=True).start()
        return True

    def _run_ui(self, on_result: Callable) -> None:
        """在独立线程里运行 tkinter 全屏选区。"""
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()

        state = {"selecting": False, "sx": 0, "sy": 0, "rect": None}

        sel = tk.Toplevel(root)
        sel.attributes("-fullscreen", True)
        sel.attributes("-alpha", 0.3)
        sel.attributes("-topmost", True)
        sel.configure(bg="gray")

        cv = tk.Canvas(sel, cursor="cross", highlightthickness=0)
        cv.pack(fill=tk.BOTH, expand=True)

        def _finish(result):
            """在独立线程中回调并销毁 root，避免 evaluate_js 阻塞 tkinter 事件循环。"""
            def _run():
                try:
                    on_result(result)
                except Exception as ex:
                    logging.error(f"[OCR] on_result 回调失败: {ex}")
                finally:
                    root.after(0, root.destroy)
            threading.Thread(target=_run, daemon=True).start()

        def on_press(e):
            state.update(selecting=True, sx=e.x, sy=e.y)
            state["rect"] = cv.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline="red", width=2, fill="blue", stipple="gray12"
            )

        def on_drag(e):
            if state["selecting"] and state["rect"]:
                cv.coords(state["rect"], state["sx"], state["sy"], e.x, e.y)

        def on_release(e):
            if not state["selecting"]:
                return
            state["selecting"] = False
            left, top_    = min(state["sx"], e.x), min(state["sy"], e.y)
            right, bottom = max(state["sx"], e.x), max(state["sy"], e.y)
            sel.destroy()

            if right - left >= 10 and bottom - top_ >= 10:
                def _do():
                    try:
                        result = perform_ocr(left, top_, right, bottom)
                    except Exception as ex:
                        logging.error(f"[OCR] 识别失败: {ex}")
                        result = []
                    _finish(result)

                threading.Thread(target=_do, daemon=True).start()
            else:
                # 选区太小，视为取消——也要通知 JS 重置 isScanning
                _finish([])

        def on_escape(e):
            sel.destroy()
            # 用户按 Escape 取消——通知 JS 重置 isScanning
            _finish([])

        cv.bind("<ButtonPress-1>",   on_press)
        cv.bind("<B1-Motion>",       on_drag)
        cv.bind("<ButtonRelease-1>", on_release)
        sel.bind("<Escape>",         on_escape)

        root.mainloop()