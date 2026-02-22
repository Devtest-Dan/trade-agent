@echo off
title Trade Control Setup
echo ============================================
echo   Trade Control - One-Time Setup
echo ============================================
echo.

REM 1. Install Python dependencies
echo [1/3] Installing Python dependencies...
pip install psutil pystray Pillow pywin32
echo.

REM 2. Generate icon
echo [2/3] Generating application icon...
python -c "from PIL import Image, ImageDraw, ImageFont; img = Image.new('RGBA', (256, 256), (0,0,0,0)); d = ImageDraw.Draw(img); d.ellipse([16,16,240,240], fill=(88,166,255,220)); d.ellipse([28,28,228,228], fill=(13,17,23,240)); d.polygon([(128,50),(170,120),(128,100),(86,120)], fill=(63,185,80,255)); d.polygon([(128,100),(170,170),(128,150),(86,170)], fill=(88,166,255,255)); d.polygon([(108,170),(128,210),(148,170)], fill=(248,81,73,200)); img.save('trade_icon.ico', format='ICO', sizes=[(256,256),(64,64),(32,32),(16,16)])"
echo.

REM 3. Create startup shortcut
echo [3/3] Creating Windows startup shortcut...
python -c "import os, sys; exec(open(os.devnull).read()) if False else None; import win32com.client; shell = win32com.client.Dispatch('WScript.Shell'); startup = shell.SpecialFolders('Startup'); lnk = os.path.join(startup, 'TradeControl.lnk'); shortcut = shell.CreateShortCut(lnk); shortcut.TargetPath = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'); shortcut.Arguments = os.path.abspath('trade_control.pyw'); shortcut.WorkingDirectory = os.path.abspath('.'); shortcut.IconLocation = os.path.abspath('trade_icon.ico'); shortcut.Description = 'Trade Control - Trade Agent Service Manager'; shortcut.save(); print(f'Shortcut created: {lnk}')"
echo.

echo ============================================
echo   Setup Complete!
echo.
echo   Trade Control will auto-start on boot.
echo   Run trade_control.pyw to start manually.
echo ============================================
pause
