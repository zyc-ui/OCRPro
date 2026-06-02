@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

echo ========================================
echo   Aero 打包工具（新版）
echo ========================================

echo [0/4] 环境检查...
python --version >nul 2>nul || (
  echo [ERROR] 未找到 Python，请先安装并加入 PATH。
  exit /b 1
)

pyinstaller --version >nul 2>nul || (
  echo [ERROR] 未找到 PyInstaller，请先执行: pip install pyinstaller
  exit /b 1
)

python -c "import PySide6" >nul 2>nul || (
  echo [ERROR] 未找到 PySide6。请先执行: pip install PySide6
  exit /b 1
)

python -c "import numpy, faiss, sentence_transformers, torch, transformers" >nul 2>nul || (
  echo [ERROR] 未找到本地向量检索依赖。请先执行:
  echo         pip install sentence-transformers faiss-cpu numpy torch transformers
  exit /b 1
)

if defined BGE_M3_MODEL_DIR (
  if not exist "%BGE_M3_MODEL_DIR%" (
    echo [ERROR] BGE_M3_MODEL_DIR 不存在: %BGE_M3_MODEL_DIR%
    exit /b 1
  ) else (
    echo [INFO] 使用 BGE_M3_MODEL_DIR=%BGE_M3_MODEL_DIR%
  )
) else (
  if exist "bge-m3-model" (
    set "BGE_M3_MODEL_DIR=%cd%\bge-m3-model"
    echo [INFO] 自动使用项目目录模型: %BGE_M3_MODEL_DIR%
  ) else if exist "E:\bge-m3-model" (
    set "BGE_M3_MODEL_DIR=E:\bge-m3-model"
    echo [INFO] 自动使用 E 盘模型: %BGE_M3_MODEL_DIR%
  ) else (
    echo [ERROR] 未找到 bge-m3 模型目录。
    echo         请执行以下任一方案后重试：
    echo         1^) 在项目根目录放置 bge-m3-model
    echo         2^) 设置环境变量 BGE_M3_MODEL_DIR 指向模型目录
    echo         3^) 确保 E:\bge-m3-model 存在
    exit /b 1
  )
)

if defined TESSERACT_DIR (
  if not exist "%TESSERACT_DIR%" (
    echo [WARN] TESSERACT_DIR 不存在: %TESSERACT_DIR%
    echo [WARN] 将继续打包，但 OCR 运行可能失败。
  ) else (
    echo [INFO] 使用 TESSERACT_DIR=%TESSERACT_DIR%
  )
) else (
  echo [INFO] 未设置 TESSERACT_DIR，将由 spec 使用默认目录。
)

echo.
echo [1/4] 清理旧文件...
if exist "dist\UMIHOSHI" rmdir /s /q "dist\UMIHOSHI"
if exist "build\UMIHOSHI" rmdir /s /q "build\UMIHOSHI"
if exist "dist\Aero" rmdir /s /q "dist\Aero"
if exist "build\Aero" rmdir /s /q "build\Aero"

echo.
echo [2/4] 开始打包...
pyinstaller --clean --noconfirm UMIHOSHI.spec
if errorlevel 1 (
  echo [ERROR] 打包过程失败，请检查上方日志。
  exit /b 1
)

echo.
echo [2.5/4] 复制外置模型到 resource...
if not exist "dist\Aero\resource" mkdir "dist\Aero\resource"
if exist "dist\Aero\resource\bge-m3-model" rmdir /s /q "dist\Aero\resource\bge-m3-model"
xcopy "%BGE_M3_MODEL_DIR%\*" "dist\Aero\resource\bge-m3-model\" /E /I /Y >nul
if errorlevel 1 (
  echo [ERROR] 复制 bge-m3 模型失败，请检查目录权限或磁盘空间。
  exit /b 1
)

echo.
echo [3/4] 校验产物...
if not exist "dist\Aero\Aero.exe" (
  echo [ERROR] 未找到 dist\Aero\Aero.exe
  exit /b 1
)

echo [OK] 打包成功。

echo.
echo [4/4] 关键文件检查...
if exist "dist\Aero\_internal\database_data.db" (
  echo [OK] database_data.db 已打包
) else (
  echo [WARN] database_data.db 未找到
)

if exist "dist\Aero\_internal\products_vector.index" (
  echo [OK] products_vector.index 已打包
) else (
  echo [WARN] products_vector.index 未找到
)

if exist "dist\Aero\_internal\products_meta.pkl" (
  echo [OK] products_meta.pkl 已打包
) else (
  echo [WARN] products_meta.pkl 未找到
)

if exist "dist\Aero\resource\bge-m3-model\config.json" (
  echo [OK] resource\bge-m3-model 已就位
) else (
  echo [WARN] resource\bge-m3-model 未找到或缺少 config.json
)

if exist "dist\Aero\_internal\sentence_transformers" (
  echo [OK] sentence_transformers 运行库已打包
) else (
  echo [WARN] sentence_transformers 未在 _internal 中找到
)

if exist "dist\Aero\_internal\frontend\index.html" (
  echo [OK] frontend 已打包
) else (
  echo [WARN] frontend/index.html 未找到
)

echo.
echo 输出目录: dist\Aero
pause
