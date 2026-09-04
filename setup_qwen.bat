@echo off
setlocal
cd /d "%~dp0"

set "OLLAMA_EXE="
where ollama >nul 2>nul && set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"

if not defined OLLAMA_EXE (
  where winget >nul 2>nul || (
    echo [ERRO] Winget nao encontrado. Instale o Ollama por https://ollama.com/download/windows
    pause
    exit /b 1
  )
  echo Instalando Ollama...
  winget install --exact --id Ollama.Ollama --accept-package-agreements --accept-source-agreements || exit /b 1
  set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
)

echo Baixando Qwen 3 8B. O download tem aproximadamente 5,2 GB...
"%OLLAMA_EXE%" pull qwen3:8b || (
  echo [ERRO] Nao foi possivel baixar o modelo.
  pause
  exit /b 1
)

echo.
echo Qwen 3 8B pronto. Abra a interface e mantenha IA contextual habilitada.
pause
endlocal
