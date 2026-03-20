@echo off
chcp 65001
echo ========================================
echo   UMIHOSHI 打包工具
echo ========================================
echo.

echo [1/2] 清理旧的打包文件...
if exist "dist\UMIHOSHI" rmdir /s /q "dist\UMIHOSHI"
if exist "build\UMIHOSHI" rmdir /s /q "build\UMIHOSHI"
echo 清理完成。
echo.

echo [2/2] 开始打包...
pyinstaller --noconfirm UMIHOSHI.spec

echo.
if exist "dist\UMIHOSHI\UMIHOSHI.exe" (
    echo ========================================
    echo   打包成功！
    echo   输出路径: dist\UMIHOSHI\UMIHOSHI.exe
    echo ========================================
) else (
    echo ========================================
    echo   打包失败，请检查上方错误信息。
    echo ========================================
)

echo.
pause