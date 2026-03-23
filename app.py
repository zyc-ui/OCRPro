"""
app.py — 应用启动入口
运行方式：python app.py
调试模式：python app.py --debug
"""

import logging
import os
import sys

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
        url              = html,
        js_api           = api,
        width            = 1440,
        height           = 860,
        min_size         = (1024, 600),
        background_color = "#ffffff",
        text_select      = True,
    )

    api.set_window(window)

    # debug=False：默认不打开 DevTools；传 --debug 时才开启
    webview.start(debug=False, http_server=False)


if __name__ == "__main__":
    main()