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
        'webview.platforms.qt',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
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
        'openpyxl',
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
        # 强制走 Qt 后端，排除 WinForms/pythonnet，避免分发机器 CLR 兼容问题
        'pythonnet',
        'clr_loader',
        'clr',
        'webview.platforms.winforms',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
        # 环境里可能存在但本项目不需要的重型 AI 依赖（避免 hooks 扫描）
        'torch',
        'torchvision',
        'torchaudio',
        'tensorflow',
        'tensorflow_estimator',
        'keras',
        'transformers',
        'onnxruntime',
        'sklearn',
        'cv2',
        'nltk',
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
