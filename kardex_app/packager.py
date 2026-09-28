# -*- coding: utf-8 -*-
"""Empacota o SQL num pacote executável que roda direto no isql, **com
contador de progresso**: o trabalho é dividido em partes (`parte_0001.sql`…) e o
driver .bat/.ps1 executa uma por uma imprimindo "Parte N/Total".

O recompute é emitido como um KARDEX_RECOMPUTA por produto (statements simples),
em lotes, para dar progresso — em vez de um único EXECUTE BLOCK que roda tudo
sem retorno. Inspirado no eagle_sql_builder, porém enxuto."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .core import RECOMPUTA_DATA, generate_recompute_statements
from .db import ConexaoConfig

FB_BIN_CANDIDATES = [
    r"C:\Program Files\Firebird\Firebird_2_5\bin",
    r"C:\Program Files\Firebird\Firebird_3_0",
    r"C:\Program Files\Firebird\Firebird_4_0",
    r"C:\Program Files\Firebird\Firebird_5_0",
    r"C:\Program Files (x86)\Firebird\Firebird_2_5\bin",
    r"C:\Program Files (x86)\Firebird\Firebird_3_0",
]

_ENCODINGS = {
    "WIN1252": "cp1252",
    "ISO8859_1": "latin-1",
    "UTF8": "utf-8",
    "NONE": "cp1252",
}

# Statements por parte: cada parte é uma chamada isql; lotes menores = progresso
# mais frequente, à custa de mais processos isql.
LOTE = 100


def encoding_para(charset: str) -> str:
    return _ENCODINGS.get((charset or "WIN1252").upper(), "cp1252")


def _connstring(cfg: ConexaoConfig) -> str:
    host = (cfg.host or "localhost").strip()
    return f"{host}/{int(cfg.port or 3050)}:{cfg.database}"


def _lotes(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def montar_partes(
    recompute_ids: list[int],
    lancamento_statements: list[str],
    lote: int = LOTE,
) -> list[str]:
    """Monta o corpo de cada parte: recompute (antes), lançamentos, recompute
    (depois), cada lote com COMMIT ao final. Devolve a lista de conteúdos."""
    rec = generate_recompute_statements(recompute_ids, RECOMPUTA_DATA)
    partes: list[str] = []
    for grupo in (rec, lancamento_statements, rec):
        for lote_stmts in _lotes(grupo, lote):
            if lote_stmts:
                partes.append("\n".join(lote_stmts) + "\nCOMMIT;\n")
    return partes


def build_bat(cfg: ConexaoConfig) -> str:
    db = _connstring(cfg)
    cs = cfg.charset or "WIN1252"
    l = [
        "@echo off",
        "chcp 1252 >nul",
        "setlocal enabledelayedexpansion",
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
        'echo Firebird: "%FBBIN%"',
        'echo [%date% %time%] ==== Execucao ==== >>"%LOG%"',
        "set /a TOTAL=0",
        'for %%f in ("%~dp0parte_*.sql") do set /a TOTAL+=1',
        "if %TOTAL%==0 echo [ERRO] Nenhuma parte encontrada. & pause & exit /b 1",
        "echo Total de partes: %TOTAL%",
        "set /a N=0",
        'for %%f in ("%~dp0parte_*.sql") do (',
        "  set /a N+=1",
        '  echo [!N!/%TOTAL%] Executando %%~nxf ...',
        '  echo [%date% %time%] [!N!/%TOTAL%] %%~nxf >>"%LOG%"',
        '  "%ISQL%" -b -c 2048 -user %USR% -password %PWD% -ch %CS% '
        '-i "%%f" "%DB%" >>"%LOG%" 2>&1',
        "  if errorlevel 1 goto err",
        ")",
        "echo Concluido com sucesso. Log em execucao.log",
        "pause",
        "exit /b 0",
        ":err",
        "echo ----------------------------------------",
        'type "%LOG%"',
        "echo ----------------------------------------",
        "echo [ERRO] isql retornou erro na parte !N!/%TOTAL% (veja execucao.log).",
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
        "$Partes = Get-ChildItem -Path $Dir -Filter 'parte_*.sql' | Sort-Object Name\r\n"
        "$Total = $Partes.Count\r\n"
        "if ($Total -eq 0) { Write-Host '[ERRO] Nenhuma parte encontrada.'; "
        "Read-Host 'ENTER para sair' | Out-Null; exit 1 }\r\n"
        "Write-Host \"Total de partes: $Total\"\r\n"
        "$n = 0\r\n"
        "foreach ($p in $Partes) {\r\n"
        "  $n++\r\n"
        "  $pct = [int](100 * $n / $Total)\r\n"
        "  Write-Progress -Activity 'Executando no isql' "
        "-Status \"Parte $n/$Total ($($p.Name))\" -PercentComplete $pct\r\n"
        "  Write-Host \"[$n/$Total] $($p.Name) ...\"\r\n"
        "  Add-Content -Path $Log -Value (\"[{0}] [{1}/{2}] {3}\" -f "
        "(Get-Date), $n, $Total, $p.Name)\r\n"
        f"  $a = @('-b','-c','2048','-user',$Usr,'-password',$Pw,'-ch',$Cs,"
        "'-i',$p.FullName,$DB)\r\n"
        "  & $ISQL @a 2>&1 | Add-Content -Path $Log\r\n"
        "  if ($LASTEXITCODE -ne 0) { Write-Host \"[ERRO] isql falhou na parte "
        "$n/$Total (veja execucao.log).\"; Read-Host 'ENTER para sair' | Out-Null; "
        "exit 1 }\r\n"
        "}\r\n"
        "Write-Progress -Activity 'Executando no isql' -Completed\r\n"
        "Write-Host 'Concluido com sucesso.'\r\n"
        "Read-Host 'ENTER para sair' | Out-Null\r\n"
    )


def write_package(
    pasta: str,
    cfg: ConexaoConfig,
    recompute_ids: list[int],
    lancamento_statements: list[str],
    lote: int = LOTE,
) -> str:
    """Grava as partes (parte_NNNN.sql) + executar.bat + executar.ps1. Devolve o
    caminho da pasta."""
    pasta_path = Path(pasta)
    pasta_path.mkdir(parents=True, exist_ok=True)

    # limpa partes antigas de uma geração anterior na mesma pasta
    for antigo in pasta_path.glob("parte_*.sql"):
        antigo.unlink()

    enc = encoding_para(cfg.charset)
    partes = montar_partes(recompute_ids, lancamento_statements, lote)
    for i, corpo in enumerate(partes, start=1):
        (pasta_path / f"parte_{i:04d}.sql").write_text(
            corpo, encoding=enc, errors="replace"
        )
    (pasta_path / "executar.bat").write_text(build_bat(cfg), encoding="cp1252")
    (pasta_path / "executar.ps1").write_text(
        build_ps1(cfg), encoding="utf-8-sig", newline=""
    )
    return str(pasta_path)
