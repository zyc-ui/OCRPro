@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

echo ========================================
echo   UMIHOSHI 打包工具
echo ========================================
echo.

:: ─── [0/4] 环境检查 ──────────────────────────────────────────────────────────
echo [0/4] 环境检查...

python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请先安装并将其加入 PATH。
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [INFO] %%v

pyinstaller --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 PyInstaller，请先执行: pip install pyinstaller
    exit /b 1
)
for /f "tokens=*" %%v in ('pyinstaller --version 2^>^&1') do echo [INFO] PyInstaller %%v

:: Tesseract 目录检查（只警告，不阻断打包）
if defined TESSERACT_DIR (
    if not exist "%TESSERACT_DIR%" (
        echo [WARN] TESSERACT_DIR 指向的目录不存在: %TESSERACT_DIR%
        echo [WARN] 将继续打包，但目标机上 OCR 功能可能不可用。
    ) else (
        echo [INFO] TESSERACT_DIR=%TESSERACT_DIR%
    )
) else (
    if exist "third_party\Tesseract" (
        echo [INFO] 未设置 TESSERACT_DIR，将使用默认目录 third_party\Tesseract
    ) else (
        echo [INFO] 未设置 TESSERACT_DIR，也未找到 third_party\Tesseract
        echo [INFO] 将继续打包，OCR 功能在目标机上可能不可用。
        echo [INFO] 如需 OCR，请执行: set TESSERACT_DIR=D:\tools\Tesseract
    )
)

:: ─── [1/4] 清理旧文件 ────────────────────────────────────────────────────────
echo.
echo [1/4] 清理旧文件...
if exist "dist\UMIHOSHI"  rmdir /s /q "dist\UMIHOSHI"
if exist "build\UMIHOSHI" rmdir /s /q "build\UMIHOSHI"
echo [OK] 清理完成。

:: ─── [2/4] 执行打包 ──────────────────────────────────────────────────────────
echo.
echo [2/4] 开始打包...
pyinstaller --clean --noconfirm UMIHOSHI.spec
if errorlevel 1 (
    echo.
    echo [ERROR] 打包过程失败，请检查上方日志。
    exit /b 1
)

:: ─── [3/4] 校验主产物 ────────────────────────────────────────────────────────
echo.
echo [3/4] 校验产物...
if not exist "dist\UMIHOSHI\UMIHOSHI.exe" (
    echo [ERROR] 未找到 dist\UMIHOSHI\UMIHOSHI.exe，打包可能未完成。
    exit /b 1
)
echo [OK] UMIHOSHI.exe 存在

:: ─── [4/4] 关键文件清单检查 ──────────────────────────────────────────────────
echo.
echo [4/4] 关键文件检查...

if exist "dist\UMIHOSHI\_internal\database_data.db" (
    echo [OK] database_data.db 已打包
) else (
    echo [WARN] _internal\database_data.db 未找到，请在运行前手动放入。
)

if exist "dist\UMIHOSHI\_internal\frontend\index.html" (
    echo [OK] frontend 已打包
) else (
    echo [WARN] _internal\frontend\index.html 未找到，应用启动后将白屏。
)

if exist "dist\UMIHOSHI\_internal\Tesseract\tesseract.exe" (
    echo [OK] Tesseract 已打包
) else (
    echo [INFO] Tesseract 未打包到产物（目标机需自行安装或通过环境变量指定）
)

:: ─── 完成摘要 ─────────────────────────────────────────────────────────────────
echo.
echo ========================================
echo   打包成功！
echo ----------------------------------------
echo   主程序:   dist\UMIHOSHI\UMIHOSHI.exe
echo   数据库:   dist\UMIHOSHI\_internal\database_data.db
echo   前端:     dist\UMIHOSHI\_internal\frontend\index.html
echo ========================================
echo.
echo 分发时，请将整个 dist\UMIHOSHI\ 文件夹拷贝到目标机器，
echo 直接运行 UMIHOSHI.exe 即可（无需安装 Python）。
echo.
pause