# -*- mode: python ; coding: utf-8 -*-
import os


# ── 可配置目录 ─────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath('.')
TESSERACT_DIR = os.environ.get('TESSERACT_DIR', os.path.join(PROJECT_ROOT, 'third_party', 'Tesseract'))


def collect_tree(src_dir: str, dst_root: str):
    """把目录递归转换为 PyInstaller datas 的 (src, dst) 二元组列表。"""
    pairs = []
    if not os.path.isdir(src_dir):
        print(f"[WARN] 目录不存在，跳过打包: {src_dir}")
        return pairs

    for root, _, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dst = dst_root if rel == '.' else os.path.join(dst_root, rel)
        for name in files:
            pairs.append((os.path.join(root, name), dst))
    return pairs


# ── 资源收集 ───────────────────────────────────────────────
frontend_datas = collect_tree(os.path.join(PROJECT_ROOT, 'frontend'), 'frontend')

if os.path.isdir(TESSERACT_DIR):
    # 目标结构: Tesseract/...
    tesseract_datas = collect_tree(TESSERACT_DIR, 'Tesseract')
    print(f"[INFO] 使用 Tesseract 目录: {TESSERACT_DIR}")
else:
    tesseract_datas = []
    print(f"[WARN] Tesseract 目录不存在: {TESSERACT_DIR}")


a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('database_data.db', '.'),
        ('images/app_icon.ico', 'images'),
        ('images/seastarEngineLogo.png', 'images'),
    ] + frontend_datas + tesseract_datas,
    hiddenimports=[
        'webview',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.font',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageGrab',
        'PIL._tkinter_finder',
        'pytesseract',
        'sqlite3',
        'threading',
        'textwrap',
        're',
        'traceback',
        'logging',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='UMIHOSHI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
