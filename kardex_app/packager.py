# -*- coding: utf-8 -*-
"""Empacota o SQL gerado num pacote executável (script.sql + executar.bat/.ps1)
que roda direto no isql do Firebird — bem mais rápido que colar no IBExpert.

Inspirado no eagle_sql_builder, porém enxuto: só o necessário para executar um
script (sem backup/paralelismo/triggers)."""
from __future__ import annotations

import os
from pathlib import Path

from .db import ConexaoConfig

# Onde procurar o isql.exe (primeiro que existir vence).
FB_BIN_CANDIDATES = [
    r"C:\Program Files\Firebird\Firebird_2_5\bin",
    r"C:\Program Files\Firebird\Firebird_3_0",
    r"C:\Program Files\Firebird\Firebird_4_0",
    r"C:\Program Files\Firebird\Firebird_5_0",
    r"C:\Program Files (x86)\Firebird\Firebird_2_5\bin",
    r"C:\Program Files (x86)\Firebird\Firebird_3_0",
]

# Charset da conexão -> codec Python para gravar o script.sql com os bytes certos.
_ENCODINGS = {
    "WIN1252": "cp1252",
    "ISO8859_1": "latin-1",
    "UTF8": "utf-8",
    "NONE": "cp1252",
}

SCRIPT_NAME = "script.sql"


def encoding_para(charset: str) -> str:
    return _ENCODINGS.get((charset or "WIN1252").upper(), "cp1252")


def _connstring(cfg: ConexaoConfig) -> str:
    host = (cfg.host or "localhost").strip()
    return f"{host}/{int(cfg.port or 3050)}:{cfg.database}"


def build_bat(cfg: ConexaoConfig) -> str:
    """.bat puro-cmd: autodetecta o isql, roda script.sql com -b (para no 1º erro),
    registra tudo em execucao.log."""
    db = _connstring(cfg)
    cs = cfg.charset or "WIN1252"
    l = [
        "@echo off",
        "chcp 1252 >nul",
        "setlocal",
        f'set "DB={db}"',
        f'set "USR={cfg.user or "SYSDBA"}"',
        f'set "PWD={cfg.password}"',
        f'set "CS={cs}"',
        'set "LOG=%~dp0execucao.log"',
    ]
    for c in FB_BIN_CANDIDATES:
        l += [f'set "FBBIN={c}"', 'if exist "%FBBIN%\\isql.exe" goto fb_ok']
    l += [
        "echo [ERRO] isql.exe nao encontrado. Ajuste o Firebird e tente de novo.",
        "pause",
        "exit /b 1",
        ":fb_ok",
        'set "ISQL=%FBBIN%\\isql.exe"',
        'echo [%time%] Firebird: "%FBBIN%"',
        'echo [%date% %time%] ==== Execucao ==== >>"%LOG%"',
        "echo Executando script.sql via isql...",
        f'"%ISQL%" -b -c 2048 -user %USR% -password %PWD% -ch %CS% '
        f'-i "%~dp0{SCRIPT_NAME}" "%DB%" >>"%LOG%" 2>&1',
        "if errorlevel 1 goto err",
        "echo Concluido com sucesso. Log em execucao.log",
        "pause",
        "exit /b 0",
        ":err",
        "echo ----------------------------------------",
        'type "%LOG%"',
        "echo ----------------------------------------",
        "echo [ERRO] isql retornou erro (veja execucao.log).",
        "pause",
        "exit /b 1",
        "",
    ]
    return "\r\n".join(l)


def build_ps1(cfg: ConexaoConfig) -> str:
    db = _connstring(cfg)
    cs = cfg.charset or "WIN1252"
    cands = ", ".join("'" + c.replace("'", "''") + "'" for c in FB_BIN_CANDIDATES)
    return (
        "trap { Write-Host \"[ERRO] $_\" -ForegroundColor Red; "
        "Read-Host 'ENTER para sair' | Out-Null; exit 1 }\r\n"
        "$Dir = Split-Path -Parent $PSCommandPath\r\n"
        f"$DB = '{db}'\r\n"
        f"$Usr = '{cfg.user or 'SYSDBA'}'; $Pw = '{cfg.password}'; $Cs = '{cs}'\r\n"
        f"$Cands = @({cands})\r\n"
        "$FBBIN = $Cands | Where-Object { Test-Path (Join-Path $_ 'isql.exe') } "
        "| Select-Object -First 1\r\n"
        "if (-not $FBBIN) { Write-Host '[ERRO] isql.exe nao encontrado.'; "
        "Read-Host 'ENTER para sair' | Out-Null; exit 1 }\r\n"
        "$ISQL = Join-Path $FBBIN 'isql.exe'\r\n"
        "$Log = Join-Path $Dir 'execucao.log'\r\n"
        "Write-Host \"Firebird: $FBBIN\"\r\n"
        "Write-Host 'Executando script.sql via isql...'\r\n"
        f"$a = @('-b','-c','2048','-user',$Usr,'-password',$Pw,'-ch',$Cs,'-i',"
        f"(Join-Path $Dir '{SCRIPT_NAME}'),$DB)\r\n"
        "& $ISQL @a 2>&1 | Tee-Object -FilePath $Log\r\n"
        "if ($LASTEXITCODE -ne 0) { Write-Host '[ERRO] isql retornou erro "
        "(veja execucao.log).'; Read-Host 'ENTER para sair' | Out-Null; exit 1 }\r\n"
        "Write-Host 'Concluido com sucesso.'\r\n"
        "Read-Host 'ENTER para sair' | Out-Null\r\n"
    )


def write_package(pasta: str, sql_content: str, cfg: ConexaoConfig) -> str:
    """Grava script.sql (na codificação do charset), executar.bat e executar.ps1
    na pasta indicada. Devolve o caminho da pasta."""
    pasta_path = Path(pasta)
    pasta_path.mkdir(parents=True, exist_ok=True)

    enc = encoding_para(cfg.charset)
    (pasta_path / SCRIPT_NAME).write_text(sql_content, encoding=enc, errors="replace")
    (pasta_path / "executar.bat").write_text(build_bat(cfg), encoding="cp1252")
    (pasta_path / "executar.ps1").write_text(
        build_ps1(cfg), encoding="utf-8-sig", newline=""
    )
    return str(pasta_path)
