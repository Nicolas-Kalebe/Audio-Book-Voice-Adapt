@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul || (
  echo [ERRO] Python Launcher nao encontrado. Instale Python 3.11 em https://python.org/
  exit /b 1
)
py -3.11 --version >nul 2>nul || (
  echo [ERRO] Python 3.11 e necessario. A versao 3.14 ainda nao e adequada aos backends de audio/VC.
  exit /b 1
)
if not exist .venv\Scripts\python.exe py -3.11 -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel || exit /b 1
python -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130 || exit /b 1
python -m pip install -e ".[transcription,audio,dev,gpu-windows]" || exit /b 1

where ffmpeg >nul 2>nul || (
  where winget >nul 2>nul && winget install --id Gyan.FFmpeg --exact --accept-source-agreements --accept-package-agreements
)
echo.
python check_gpu.py
echo.
echo Ambiente principal instalado. Feche e abra o terminal se o FFmpeg acabou de ser instalado.
echo Para instalar o backend de conversao zero-shot, execute setup_seedvc.bat.
endlocal
