# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.datastruct import Tree

block_cipher = None

# ── Tesseract 目录解析 ────────────────────────────────────────────────────────
# 优先读取环境变量 TESSERACT_DIR，否则回退 ./third_party/Tesseract
TESSERACT_DIR = os.environ.get(
    'TESSERACT_DIR',
    os.path.join('third_party', 'Tesseract')
)

tesseract_datas = []
if os.path.isdir(TESSERACT_DIR):
    for root, dirs, files in os.walk(TESSERACT_DIR):
        for f in files:
            full_path = os.path.join(root, f)
            # 保持 Tesseract/xxx 相对结构
            rel_dir = os.path.relpath(root, os.path.dirname(TESSERACT_DIR))
            tesseract_datas.append((full_path, rel_dir))
    print(f"[Spec] Tesseract 已加入打包: {TESSERACT_DIR}")
else:
    print(f"[WARN] Tesseract 目录不存在: {TESSERACT_DIR}")
    print("[WARN] 将继续打包，但目标机上 OCR 功能可能不可用。")
    print("[WARN] 如需打包 OCR，请设置 TESSERACT_DIR 环境变量或将 Tesseract 放入 third_party/Tesseract。")

# ── 隐藏依赖 ─────────────────────────────────────────────────────────────────
hidden = [
    # pywebview
    'webview',
    # tkinter
    'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
    'tkinter.messagebox', 'tkinter.font',
    # PIL / Pillow
    'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageGrab', 'PIL._tkinter_finder',
    # OCR
    'pytesseract',
    # 数据库
    'sqlite3',
    # 剪贴板
    'pyperclip',
    # Windows 剪贴板（HTML 复制）
    'win32clipboard', 'win32con', 'win32api', 'pywintypes',
    # 网络请求（RFQ 解析）
    'requests', 'bs4', 'lxml',
    # 邮件
    'email', 'email.mime', 'email.mime.multipart', 'email.mime.text',
    # 标准库
    'threading', 'textwrap', 're', 'traceback', 'logging', 'webbrowser',
] + collect_submodules('webview')

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['app.py'],                  # ← 入口已从 main.py 改为 app.py
    pathex=['.'],
    binaries=[],
    datas=[
        # 数据库（进入 _internal，与 config.py 读取路径一致）
        ('database_data.db', '.'),
        # 图片资源
        ('images/app_icon.ico',          'images'),
        ('images/seastarEngineLogo.png', 'images'),
        # 项目自身包标记
        ('__init__.py', '.'),
    ]
    # 前端目录完整拷贝到 _internal/frontend
    + list(Tree('frontend', prefix='frontend'))
    # Tesseract 整目录（目录存在时生效）
    + tesseract_datas,

    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    # 排除确认不需要的大型包
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'IPython', 'jupyter', 'notebook', 'pytest', 'setuptools',
    ],

    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # onedir 模式（exe + dll 分离）
    name='UMIHOSHI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # 关闭 UPX，避免杀毒误报
    console=False,              # 不显示控制台
    icon='images/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='UMIHOSHI',
)
