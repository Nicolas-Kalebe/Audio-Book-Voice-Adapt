@echo off
setlocal
cd /d "%~dp0"
where git >nul 2>nul || (echo [ERRO] Git nao encontrado.& exit /b 1)
py -3.10 --version >nul 2>nul || (
  echo [ERRO] Seed-VC recomenda Python 3.10. Instale-o com: winget install Python.Python.3.10
  exit /b 1
)
if not exist models\seed-vc\.git git clone https://github.com/Plachtaa/seed-vc.git models\seed-vc || exit /b 1
if not exist models\seed-vc\.venv\Scripts\python.exe py -3.10 -m venv models\seed-vc\.venv || exit /b 1
call models\seed-vc\.venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel "setuptools<82" || exit /b 1
rem O requirements oficial ainda fixa PyTorch 2.4/cu126, anterior ao suporte Blackwell.
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130 || exit /b 1
rem resemblyzer pede o webrtcvad antigo, que exige Visual C++; o fork wheels exporta o mesmo modulo/API.
python -m pip install webrtcvad-wheels resemblyzer typing --no-deps || exit /b 1
findstr /v /r /c:"^torch " /c:"^torch==" /c:"^torchvision" /c:"^torchaudio" /c:"^resemblyzer" models\seed-vc\requirements.txt > models\seed-vc\requirements-blackwell.txt
python -m pip install -r models\seed-vc\requirements-blackwell.txt || exit /b 1
del models\seed-vc\requirements-blackwell.txt >nul 2>nul
rem pip check nao reconhece que webrtcvad-wheels fornece o modulo webrtcvad; valide imports reais.
python -c "import torch, torchaudio, torchvision, webrtcvad; from resemblyzer import VoiceEncoder; assert torch.cuda.is_available(); print(torch.__version__, torch.cuda.get_device_name(0))" || exit /b 1
echo Seed-VC instalado. Os checkpoints serao baixados no primeiro uso.
endlocal
