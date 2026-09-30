# -*- coding: utf-8 -*-
"""Preparação dos lançamentos (consultas ao banco) fora da thread da interface.

As consultas — listar produtos, estoque na data, preços — podem demorar em
bases grandes e, se rodassem na thread da GUI, travavam a janela sem feedback.
Aqui a lógica é headless (sem widgets): recebe a conexão/config e devolve
(unidades, info); o worker roda numa thread com uma janela de progresso."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .core import (
    RECOMPUTA_INICIO,
    achatar,
    generate_bulk_units,
    generate_recompute_units,
    generate_sql_statements,
    generate_zero_statements,
)
from .db import (
    ConexaoConfig,
    DBError,
    conectar,
    estoque_e_preco_todos,
    estoque_na_data,
    listar_produtos_ativos,
    listar_todos_produtos,
    pids_do_lancamento,
    sql_delete_lancamento,
)


def _info_base() -> dict:
    return {"contados": 0, "fora": 0, "iguais": 0, "zerados": 0,
            "ja_zerados": 0}


def preparar_sem_banco(agregadas, history, date_str):
    """Modo procedure sem nenhum filtro que dependa do banco."""
    count = generate_sql_statements(agregadas, history, date_str)
    units = [(str(r.produtos_id), [s]) for r, s in zip(agregadas, count)]
    info = _info_base()
    info["contados"] = len(agregadas)
    return units, info


def _prep_procedure(conn, agregadas, history, date_str, zerar, pular_iguais):
    info = _info_base()
    produtos = set(listar_todos_produtos(conn))

    antes = len(agregadas)
    existentes = [r for r in agregadas if r.produtos_id in produtos]
    info["fora"] = antes - len(existentes)
    contados_ids = {r.produtos_id for r in existentes}

    if pular_iguais:
        est = estoque_na_data(conn, [r.produtos_id for r in existentes], date_str)
        antes = len(existentes)
        existentes = [
            r for r in existentes
            if round(r.quantidade, 5) != round(est.get(r.produtos_id, 0.0), 5)
        ]
        info["iguais"] = antes - len(existentes)

    info["contados"] = len(existentes)
    count = generate_sql_statements(existentes, history, date_str)
    units = [(str(r.produtos_id), [s]) for r, s in zip(existentes, count)]

    if zerar:
        ativos = listar_produtos_ativos(conn)
        nao_contados = sorted(ativos - contados_ids)
        est_zero = estoque_na_data(conn, nao_contados, date_str)
        a_zerar = [
            pid for pid in nao_contados
            if round(est_zero.get(pid, 0.0), 5) != 0
        ]
        info["ja_zerados"] = len(nao_contados) - len(a_zerar)
        zero = generate_zero_statements(a_zerar, history, date_str)
        units += [(str(pid), [s]) for pid, s in zip(a_zerar, zero)]
        info["zerados"] = len(zero)

    return units, info


def _prep_lote(conn, agregadas, history, date_str, zerar):
    produtos = set(listar_todos_produtos(conn))
    ativos = listar_produtos_ativos(conn) if zerar else set()
    dados = estoque_e_preco_todos(conn, date_str)

    existentes = [r for r in agregadas if r.produtos_id in produtos]
    fora = len(agregadas) - len(existentes)
    contados_ids = {r.produtos_id for r in existentes}

    alvos = {r.produtos_id: r.quantidade for r in existentes}
    if zerar:
        for pid in ativos - contados_ids:
            alvos[pid] = 0.0

    estoque = {pid: v[0] for pid, v in dados.items()}
    preco = {pid: v[1] for pid, v in dados.items()}
    units, binfo = generate_bulk_units(alvos, estoque, preco, history, date_str)

    info = _info_base()
    info.update({
        "contados": len(contados_ids),
        "fora": fora,
        "lote": True,
        "lancados": binfo["lancados"],
        "delta_zero": binfo["pulados_delta_zero"],
    })
    return units, info


def preparar_no_banco(cfg: ConexaoConfig, agregadas, history, date_str,
                      modo_lote: bool, zerar: bool, pular_iguais: bool,
                      recompute_antes: bool = False):
    """Abre a conexão, monta as unidades e devolve (units, info). Levanta
    DBError em falha (o chamador trata). Com `recompute_antes`, inclui em
    info['pre_units'] o recompute de todos os produtos (desde o início) — para
    corrigir saldos divergentes antes dos ajustes."""
    conn = None
    try:
        conn = conectar(cfg)
        if modo_lote:
            units, info = _prep_lote(conn, agregadas, history, date_str, zerar)
        else:
            units, info = _prep_procedure(
                conn, agregadas, history, date_str, zerar, pular_iguais
            )
        if recompute_antes:
            ids = listar_todos_produtos(conn)
            info["pre_units"] = generate_recompute_units(ids, RECOMPUTA_INICIO)
        return units, info
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def preparar_desfazer(cfg: ConexaoConfig, date_str: str, history: str):
    """Localiza os movimentos a desfazer (data/hora + histórico) e monta:
    pre_units = [DELETE], units = recompute dos produtos afetados. Devolve
    (pre_units, units, n_afetados)."""
    conn = None
    try:
        conn = conectar(cfg)
        hist = history.strip().upper()
        pids = pids_do_lancamento(conn, date_str, hist)
        if not pids:
            return [], [], 0
        delete_sql = sql_delete_lancamento(date_str, hist)
        pre_units = [(f"Excluir movimentos ({len(pids)} produto(s))",
                      [delete_sql])]
        units = generate_recompute_units(pids, date_str)
        return pre_units, units, len(pids)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class PreparacaoWorker(QThread):
    """Roda `preparar_no_banco` numa thread, para a interface não travar."""
    concluido = Signal(object, object)   # (units, info)
    erro = Signal(str)

    def __init__(self, cfg, agregadas, history, date_str,
                 modo_lote, zerar, pular_iguais, recompute_antes=False,
                 parent=None):
        super().__init__(parent)
        self._args = (cfg, agregadas, history, date_str,
                      modo_lote, zerar, pular_iguais, recompute_antes)

    def run(self) -> None:
        try:
            units, info = preparar_no_banco(*self._args)
        except DBError as exc:
            self.erro.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"Falha ao preparar: {exc}")
            return
        self.concluido.emit(units, info)


class DesfazerPrepWorker(QThread):
    """Roda `preparar_desfazer` numa thread (localiza e monta o DELETE)."""
    concluido = Signal(object)   # (pre_units, units, n)
    erro = Signal(str)

    def __init__(self, cfg, date_str, history, parent=None):
        super().__init__(parent)
        self._args = (cfg, date_str, history)

    def run(self) -> None:
        try:
            pre_units, units, n = preparar_desfazer(*self._args)
        except DBError as exc:
            self.erro.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.erro.emit(f"Falha ao localizar lançamentos: {exc}")
            return
        self.concluido.emit((pre_units, units, n))
