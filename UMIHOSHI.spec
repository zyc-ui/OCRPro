# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# ── Tesseract 整目录（打包进去） ──────────────────────────
TESSERACT_DIR = r"E:\Tesseract"

tesseract_datas = []
if os.path.isdir(TESSERACT_DIR):
    for root, dirs, files in os.walk(TESSERACT_DIR):
        for f in files:
            full_path = os.path.join(root, f)
            # 目标相对路径：保持 Tesseract/xxx 结构
            rel_dir = os.path.relpath(root, os.path.dirname(TESSERACT_DIR))
            tesseract_datas.append((full_path, rel_dir))

# ── Analysis ──────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # 项目自身文件
        ('__init__.py',          '.'),
        ('DatabaseUpdate.py',    '.'),
        # 数据库放到 exe 同级，方便用户替换更新
        # 注意：这里的目标路径 '.' 在 onedir 模式下实际是 _internal，
        # 所以改用 runtime hook 或直接让用户把 db 放 exe 旁边
        ('database_data.db',     '.'),
        # 图片资源
        ('images/app_icon.ico',         'images'),
        ('images/seastarEngineLogo.png','images'),
    ] + tesseract_datas,

    hiddenimports=[
        # tkinter
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.font',
        # PIL / Pillow
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageGrab',
        'PIL._tkinter_finder',
        # OCR
        'pytesseract',
        # GUI 自动化
        'pyautogui',
        # 数据库
        'sqlite3',
        # 剪贴板
        'pyperclip',
        # Windows 剪贴板（HTML 复制）
        'win32clipboard',
        'win32con',
        'win32api',
        'pywintypes',
        # 邮件
        'email',
        'email.mime',
        'email.mime.multipart',
        'email.mime.text',
        # 其他标准库
        'threading',
        'textwrap',
        're',
        'traceback',
        'logging',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    # 排除不需要的大型包，减小体积
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
    exclude_binaries=True,      # onedir 模式（exe + dll 分离，更稳定）
    name='UMIHOSHI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # 关闭 UPX，避免杀毒误报
    console=False,              # 不显示黑色控制台
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