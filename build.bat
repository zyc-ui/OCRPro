@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

echo ========================================
echo   UMIHOSHI 打包工具（新版）
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

echo.
echo [2/4] 开始打包...
pyinstaller --clean --noconfirm UMIHOSHI.spec
if errorlevel 1 (
  echo [ERROR] 打包过程失败，请检查上方日志。
  exit /b 1
)

echo.
echo [3/4] 校验产物...
if not exist "dist\UMIHOSHI\UMIHOSHI.exe" (
  echo [ERROR] 未找到 dist\UMIHOSHI\UMIHOSHI.exe
  exit /b 1
)

echo [OK] 打包成功。

echo.
echo [4/4] 关键文件检查...
if exist "dist\UMIHOSHI\_internal\database_data.db" (
  echo [OK] database_data.db 已打包
) else (
  echo [WARN] database_data.db 未找到
)

if exist "dist\UMIHOSHI\_internal\frontend\index.html" (
  echo [OK] frontend 已打包
) else (
  echo [WARN] frontend/index.html 未找到
)

echo.
echo 输出目录: dist\UMIHOSHI
pause
