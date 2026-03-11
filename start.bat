@ECHO OFF
title DUCKHUNT - [CLI]

REM Configura variaveis do MinGW
SET "MINGW_HOME=%~dp0mingw64"
SET "PATH=%MINGW_HOME%\bin;%PATH%"

REM Configura compiladores
SET "CC=%MINGW_HOME%\bin\x86_64-w64-mingw32-gcc.exe"
SET "CXX=%MINGW_HOME%\bin\x86_64-w64-mingw32-g++.exe"
SET "FC=%MINGW_HOME%\bin\x86_64-w64-mingw32-gfortran.exe"
SET "LD=%MINGW_HOME%\bin\ld.exe"
SET "AR=%MINGW_HOME%\bin\x86_64-w64-mingw32-gcc-ar.exe"
SET "RANLIB=%MINGW_HOME%\bin\x86_64-w64-mingw32-gcc-ranlib.exe"
SET "WINDRES=%MINGW_HOME%\bin\windres.exe"
SET "STRIP=%MINGW_HOME%\bin\strip.exe"
SET "PKG_CONFIG=%MINGW_HOME%\bin\pkgconf.exe"

REM Variaveis para garantir que o llama-cpp-python use o MinGW
SET "CMAKE_GENERATOR=MinGW Makefiles"
SET "CMAKE_C_COMPILER=%CC%"
SET "CMAKE_CXX_COMPILER=%CXX%"
SET "FORCE_CMAKE=1"

:check_venv
IF EXIST ".venv" GOTO run_app

IF NOT EXIST ".venv" (
    ECHO Criando ambiente virtual...
    python -m venv .venv
    IF %ERRORLEVEL% NEQ 0 (
        ECHO Erro ao criar ambiente virtual.
        PAUSE
        EXIT /B
    )
)

:install_dependencies
ECHO Verificando dependencias...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

:run_app
.venv\Scripts\python.exe app.py
PAUSE