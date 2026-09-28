# -*- coding: utf-8 -*-
"""Conexão com Firebird 2.5 e verificação de códigos contra PRODUTOS /
PRODUTOSREFERENCIAS.

A contagem pode trazer o código interno do produto (``PRODUTOS.PRODUTOS_ID``,
inteiro) ou uma referência/EAN (``PRODUTOSREFERENCIAS.PRODUTO_REFERENCIA``,
texto que aponta para um PRODUTOS_ID). Esta verificação diz, para cada código,
se ele existe como produto, como referência (resolvendo o PRODUTOS_ID) ou se
não foi encontrado.

O acesso ao banco fica isolado aqui: a classificação (`verificar_codigos`) só
depende de um objeto com `.cursor()` no padrão DB-API, o que mantém a lógica
testável sem um Firebird de verdade.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Limite conservador de parâmetros por IN (...) — o FB 2.5 estoura a XSQLDA
# bem antes de mil; 250 por lote é folgado e seguro.
CHUNK = 250

CHARSETS = ["WIN1252", "ISO8859_1", "UTF8", "NONE"]


@dataclass
class ConexaoConfig:
    host: str = "localhost"
    port: int = 3050
    database: str = ""
    user: str = "SYSDBA"
    password: str = "masterkey"
    charset: str = "WIN1252"


class DBError(Exception):
    """Falha de conexão ou consulta ao banco."""


@dataclass
class VerificacaoResultado:
    total: int = 0
    em_produtos: set[str] = field(default_factory=set)      # código == PRODUTOS_ID
    em_referencias: dict[str, int] = field(default_factory=dict)  # ref -> PRODUTOS_ID
    ausentes: list[str] = field(default_factory=list)

    @property
    def encontrados(self) -> int:
        return len(self.em_produtos) + len(self.em_referencias)


def _fbclient_embutido() -> Optional[str]:
    """Caminho da fbclient.dll embutida no executável (PyInstaller), se houver.
    Rodando do código-fonte devolve None e o fdb usa a busca padrão do sistema."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    caminho = os.path.join(base, "fbclient.dll")
    return caminho if os.path.exists(caminho) else None


def conectar(config: ConexaoConfig):
    """Abre a conexão Firebird. Importa `fdb` de forma tardia para o app rodar
    sem o driver quando a verificação não é usada."""
    try:
        import fdb
    except ImportError as exc:  # driver ausente
        raise DBError(
            "O driver 'fdb' não está instalado. Instale com: pip install fdb "
            "(requer também a biblioteca cliente do Firebird, fbclient)."
        ) from exc

    # No executável empacotado, aponta o fdb para a fbclient.dll embutida —
    # senão ele dependeria de um Firebird instalado na máquina.
    dll = _fbclient_embutido()
    if dll:
        try:
            fdb.load_api(dll)
        except Exception:
            pass  # se falhar, o fdb cai na busca padrão

    if not config.database.strip():
        raise DBError("Informe o caminho (ou alias) do banco de dados.")

    try:
        return fdb.connect(
            host=config.host or "localhost",
            port=int(config.port or 3050),
            database=config.database,
            user=config.user or "SYSDBA",
            password=config.password or "",
            charset=config.charset or "WIN1252",
        )
    except Exception as exc:  # fdb.DatabaseError e afins
        raise DBError(f"Não foi possível conectar: {exc}") from exc


def _lotes(seq: list, tamanho: int) -> Iterable[list]:
    for i in range(0, len(seq), tamanho):
        yield seq[i : i + tamanho]


def _normalizar_codigos(codigos: Iterable) -> list[str]:
    vistos: dict[str, None] = {}
    for c in codigos:
        if c is None:
            continue
        texto = str(c).strip()
        if texto and texto not in vistos:
            vistos[texto] = None
    return list(vistos.keys())


def _so_inteiros(codigos: list[str]) -> list[str]:
    inteiros = []
    for c in codigos:
        try:
            int(c)
        except (TypeError, ValueError):
            continue
        inteiros.append(c)
    return inteiros


def verificar_codigos(conn, codigos: Iterable) -> VerificacaoResultado:
    """Classifica cada código: em PRODUTOS (por PRODUTOS_ID), em
    PRODUTOSREFERENCIAS (por PRODUTO_REFERENCIA, resolvendo o PRODUTOS_ID) ou
    ausente. Um código pode existir como produto e como referência; a
    prioridade de resolução é o produto direto."""
    lista = _normalizar_codigos(codigos)
    resultado = VerificacaoResultado(total=len(lista))
    if not lista:
        return resultado

    cur = conn.cursor()

    # ---- PRODUTOS (só faz sentido consultar os que são inteiros) ----------
    inteiros = _so_inteiros(lista)
    for lote in _lotes(inteiros, CHUNK):
        marcadores = ", ".join(["?"] * len(lote))
        sql = f"SELECT PRODUTOS_ID FROM PRODUTOS WHERE PRODUTOS_ID IN ({marcadores})"
        try:
            cur.execute(sql, [int(x) for x in lote])
            for (pid,) in cur.fetchall():
                resultado.em_produtos.add(str(pid))
        except Exception as exc:
            raise DBError(f"Falha ao consultar PRODUTOS: {exc}") from exc

    # ---- PRODUTOSREFERENCIAS (comparação textual) -------------------------
    faltam = [c for c in lista if c not in resultado.em_produtos]
    for lote in _lotes(faltam, CHUNK):
        marcadores = ", ".join(["?"] * len(lote))
        sql = (
            "SELECT PRODUTO_REFERENCIA, PRODUTOS_ID FROM PRODUTOSREFERENCIAS "
            f"WHERE PRODUTO_REFERENCIA IN ({marcadores})"
        )
        try:
            cur.execute(sql, list(lote))
            for referencia, pid in cur.fetchall():
                ref = str(referencia).strip()
                if pid is not None:
                    resultado.em_referencias[ref] = int(pid)
        except Exception as exc:
            raise DBError(f"Falha ao consultar PRODUTOSREFERENCIAS: {exc}") from exc

    achados = resultado.em_produtos | set(resultado.em_referencias.keys())
    resultado.ausentes = [c for c in lista if c not in achados]
    return resultado
