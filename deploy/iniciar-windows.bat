@echo off
REM Inicia o Painel de Propagandas no Windows.
REM Para iniciar junto com o Windows: aperte Win+R, digite shell:startup
REM e coloque um atalho para este arquivo na pasta que abrir.
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    python -m venv .venv || goto erro
)
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto erro

REM Arquivo de configuracao (nome da marca, e-mail, Asaas...). Edite com o Bloco de Notas.
if not exist configuracao.env copy configuracao.env.exemplo configuracao.env >nul

:loop
".venv\Scripts\python.exe" servidor.py
echo O servidor parou. Reiniciando em 5 segundos...
timeout /t 5 /nobreak >nul
goto loop

:erro
echo Nao foi possivel instalar. Verifique se o Python esta instalado (python.org).
pause
