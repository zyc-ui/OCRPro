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

    # 在 Windows 上强制使用 Qt 后端，避免默认 WinForms 依赖 pythonnet/.NET，
    # 打包到其他机器时更稳定（不依赖目标机 CLR 环境）。
    gui = "qt" if sys.platform.startswith("win") else None
    logging.info("启动 WebView，gui=%s", gui or "auto")

    # debug=False：默认不打开 DevTools；传 --debug 时才开启
    webview.start(debug=False, http_server=False, gui=gui)


if __name__ == "__main__":
    main()
