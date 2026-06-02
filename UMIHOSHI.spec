# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import (
    collect_all,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


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
extra_binaries = []
extra_datas = []
vector_hiddenimports = []

# bge-m3 / sentence-transformers 运行时依赖（tokenizer 配置、模型卡片等）
for _pkg in ('sentence_transformers', 'transformers', 'tokenizers', 'huggingface_hub'):
    try:
        _d, _b, _h = collect_all(_pkg)
        extra_datas += _d
        extra_binaries += _b
        vector_hiddenimports += _h
        print(f"[INFO] collect_all({_pkg}): {len(_d)} datas, {len(_b)} binaries, {len(_h)} hidden")
    except Exception as e:
        print(f"[WARN] collect_all({_pkg}) 失败: {e}")
        try:
            extra_datas += copy_metadata(_pkg)
        except Exception as e2:
            print(f"[WARN] copy_metadata({_pkg}) 失败: {e2}")

try:
    import faiss

    faiss_dir = os.path.dirname(faiss.__file__)
    faiss_parent = os.path.dirname(faiss_dir)
    faiss_cpu_libs_dir = os.path.join(faiss_parent, 'faiss_cpu.libs')

    # faiss 主包的动态库
    extra_binaries += collect_dynamic_libs('faiss')
    # pip 的 faiss-cpu wheel 常把依赖 DLL 放在 faiss_cpu.libs
    extra_binaries += collect_tree(faiss_cpu_libs_dir, 'faiss_cpu.libs')
except Exception as e:
    print(f"[WARN] 收集 faiss 动态库失败，可能导致运行时缺少 DLL: {e}")

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
    binaries=extra_binaries,
    datas=[
        ('database_data.db', '.'),
        ('products_vector.index', '.'),
        ('products_meta.pkl', '.'),
        ('images/app_icon.ico', 'images'),
        ('images/seastarEngineLogo.png', 'images'),
    ] + frontend_datas + tesseract_datas + extra_datas,
    hiddenimports=[
        # FullListUpdate 运行时动态导入模块（必须显式声明）
        'DatabaseUpdate',
        'build_product_vectordb',
        'local_vector_matcher',
        'matcher',
        'vector_matcher',
        'Rfq_quotation_tool',
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.qt',
        'webview.http',
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
        'numpy',
        'faiss',
        'sentence_transformers',
        'transformers',
        'tokenizers',
        'huggingface_hub',
        'safetensors',
        'regex',
        'torch',
        'sklearn',
        'scipy',
        'pandas',
        'anthropic',
        'tqdm',
        'joblib',
        'threadpoolctl',
        'sqlite3',
        'threading',
        'textwrap',
        're',
        'traceback',
        'logging',
    ] + collect_submodules('jaraco') + collect_submodules('anthropic') + vector_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 强制走 Qt 后端，排除 WinForms/pythonnet，避免分发机器 CLR 兼容问题
        'pythonnet',
        'clr_loader',
        'clr',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        # 环境里可能存在但本项目不需要的重型 AI 依赖（避免 hooks 扫描）
        'torchvision',
        'torchaudio',
        'tensorflow',
        'tensorflow_estimator',
        'keras',
        'onnxruntime',
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
    name='Aero',
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
    name='Aero',
)
