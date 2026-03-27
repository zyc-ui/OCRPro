"""
app.py — 应用启动入口
运行方式：python app.py
调试模式：python app.py --debug
"""

import logging
import os
import sys
from pathlib import Path

import webview

from api import API


logging.basicConfig(
    level   = logging.DEBUG,
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers = [
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def _frontend_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "frontend", "index.html")


def _frontend_url(path: str) -> str:
    # Qt WebEngine 对本地文件使用 file:// URI 更稳定（尤其在中文路径场景下）
    return Path(path).resolve().as_uri()


def _resolve_gui_backend() -> str | None:
    """
    选择 pywebview 后端。

    - 默认在 Windows 优先使用 EdgeChromium，避免自动选择到 WinForms 后要求 pythonnet。
    - 若环境变量显式指定 qt，则仍可强制 Qt。
    - 可通过环境变量 OCRPRO_WEBVIEW_GUI 覆盖（如 qt / edgechromium / cef / auto）。
    """
    raw = os.getenv("OCRPRO_WEBVIEW_GUI", "").strip().lower()
    if not raw or raw == "auto":
        if sys.platform.startswith("win"):
            return "edgechromium"
        return None
    return raw


def main() -> None:
    api   = API()
    # DevTools 默认永远关闭；如需调试请临时将 False 改为 True
    debug = False
    html  = _frontend_path()

    if not os.path.exists(html):
        logging.error(f"前端文件不存在: {html}，请先完成前端层开发")
        sys.exit(1)

    window = webview.create_window(
        title            = "Seastar",
        url              = _frontend_url(html),
        js_api           = api,
        width            = 1440,
        height           = 860,
        min_size         = (1024, 600),
        background_color = "#ffffff",
        text_select      = True,
    )

    api.set_window(window)

    # 默认使用 _resolve_gui_backend 的平台策略；可用 OCRPRO_WEBVIEW_GUI 强制覆盖。
    gui = _resolve_gui_backend()
    logging.info("启动 WebView，gui=%s", gui or "auto")

    try:
        # debug=False：默认不打开 DevTools；传 --debug 时才开启
        webview.start(debug=False, http_server=False, gui=gui)
    except Exception:
        logging.exception("WebView 启动失败（gui=%s）", gui or "auto")
        raise


if __name__ == "__main__":
    main()
