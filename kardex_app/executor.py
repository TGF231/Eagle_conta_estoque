# -*- coding: utf-8 -*-
"""Execução dos lançamentos direto no banco (via fdb), numa thread, com barra de
progresso, tempo, throughput e estatísticas de transação/servidor.

Alternativa ao pacote .bat/.ps1: em vez de gerar scripts, roda aqui e o usuário
acompanha o andamento em tempo real."""
from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .db import ConexaoConfig, DBError, conectar
from .packager import FB_BIN_CANDIDATES


def _connstring(cfg: ConexaoConfig) -> str:
    host = (cfg.host or "localhost").strip()
    return f"{host}/{int(cfg.port or 3050)}:{cfg.database}"


def _localizar(nome: str):
    for d in FB_BIN_CANDIDATES:
        caminho = os.path.join(d, nome)
        if os.path.exists(caminho):
            return caminho
    return None


def _coletar_stats(con) -> dict:
    """Estatísticas de transação/servidor que evoluem durante a execução.
    Best-effort: qualquer item que falhe é omitido."""
    stats: dict = {}
    for chave, getter in (
        ("oit", lambda: con.oit),
        ("oat", lambda: con.oat),
        ("ost", lambda: con.ost),
        ("next", lambda: con.next_transaction),
        ("ativas", con.get_active_transaction_count),
    ):
        try:
            stats[chave] = getter()
        except Exception:
            pass
    try:
        stats["io"] = dict(con.io_stats())
    except Exception:
        pass
    return stats


class ExecucaoWorker(QThread):
    progresso = Signal(int, int, float)   # feito, total, segundos decorridos
    estatisticas = Signal(dict)
    mensagem = Signal(str)
    terminou = Signal(bool, str)          # sucesso, texto

    def __init__(self, cfg: ConexaoConfig, statements: list[str],
                 commit_interval: int, backup_path: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._stmts = statements
        self._commit = max(1, int(commit_interval or 1))
        self._backup_path = backup_path
        self._cancelar = False

    def cancelar(self) -> None:
        self._cancelar = True

    def _fazer_backup(self) -> bool:
        """Roda gbak antes dos lançamentos. Devolve True se OK (ou nada a
        fazer), False se falhou (o chamador aborta)."""
        if not self._backup_path:
            return True
        gbak = _localizar("gbak.exe")
        if not gbak:
            self.terminou.emit(
                False, "gbak.exe não encontrado — instale o Firebird ou "
                "desmarque o backup."
            )
            return False
        self.mensagem.emit("Gerando backup (gbak)…")
        args = [
            gbak, "-b", "-g",
            "-user", self._cfg.user or "SYSDBA",
            "-password", self._cfg.password or "",
            _connstring(self._cfg), self._backup_path,
        ]
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, creationflags=flags
            )
        except Exception as exc:
            self.terminou.emit(False, f"Falha ao rodar o gbak: {exc}")
            return False
        saida = (r.stdout or "") + (r.stderr or "")
        if saida.strip():
            self.mensagem.emit(saida.strip())
        if r.returncode != 0:
            self.terminou.emit(False, "Backup falhou — execução abortada.")
            return False
        self.mensagem.emit(f"Backup gerado: {self._backup_path}")
        return True

    def run(self) -> None:
        total = len(self._stmts)
        con = None
        t0 = time.monotonic()
        try:
            if not self._fazer_backup():
                return
            con = conectar(self._cfg)
            try:
                self.mensagem.emit(f"Conectado: {con.server_version}")
            except Exception:
                self.mensagem.emit("Conectado.")
            cur = con.cursor()
            feito = 0
            for i, sql in enumerate(self._stmts, start=1):
                if self._cancelar:
                    con.rollback()
                    self.terminou.emit(
                        False, f"Cancelado após {feito} de {total} (rollback)."
                    )
                    return
                cur.execute(sql)
                feito = i
                if i % self._commit == 0:
                    con.commit()
                    self.estatisticas.emit(_coletar_stats(con))
                if i % 20 == 0 or i == total:
                    self.progresso.emit(feito, total, time.monotonic() - t0)
            con.commit()
            self.estatisticas.emit(_coletar_stats(con))
            self.progresso.emit(total, total, time.monotonic() - t0)
            self.terminou.emit(
                True,
                f"Concluído: {total} lançamento(s) em "
                f"{time.monotonic() - t0:.1f}s.",
            )
        except DBError as exc:
            if con is not None:
                try:
                    con.rollback()
                except Exception:
                    pass
            self.terminou.emit(False, str(exc))
        except Exception as exc:  # erro de SQL/execução
            if con is not None:
                try:
                    con.rollback()
                except Exception:
                    pass
            self.terminou.emit(False, f"Erro na execução: {exc}")
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass


class ExecucaoDialog(QDialog):
    def __init__(self, cfg: ConexaoConfig, statements: list[str],
                 commit_interval: int, backup_path: str | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Executar no banco")
        self.resize(620, 560)
        self._total = len(statements)
        self._t0 = time.monotonic()
        self._worker = ExecucaoWorker(
            cfg, statements, commit_interval, backup_path, self
        )
        self._build_ui()
        if backup_path:
            # backup não tem % conhecida: barra em modo indeterminado até o
            # primeiro progresso da execução
            self.barra.setRange(0, 0)
        self._ligar()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)
        self._worker.start()

    def _build_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 14, 16, 14)
        raiz.setSpacing(12)

        titulo = QLabel("Executando no banco")
        titulo.setProperty("role", "titulo")
        raiz.addWidget(titulo)

        self.barra = QProgressBar()
        self.barra.setRange(0, self._total)
        self.barra.setFormat("%p%  (%v/%m)")
        raiz.addWidget(self.barra)

        prog = QGroupBox("Progresso")
        pf = QFormLayout(prog)
        pf.setContentsMargins(12, 8, 12, 12)
        self.lbl_tempo = QLabel("0,0 s")
        self.lbl_taxa = QLabel("—")
        self.lbl_eta = QLabel("—")
        pf.addRow("Tempo decorrido:", self.lbl_tempo)
        pf.addRow("Velocidade:", self.lbl_taxa)
        pf.addRow("Restante (ETA):", self.lbl_eta)
        raiz.addWidget(prog)

        est = QGroupBox("Estatísticas de transação / servidor")
        ef = QFormLayout(est)
        ef.setContentsMargins(12, 8, 12, 12)
        self.lbl_trans = QLabel("—")
        self.lbl_ativas = QLabel("—")
        self.lbl_io = QLabel("—")
        ef.addRow("OIT / OAT / OST / Próx.:", self.lbl_trans)
        ef.addRow("Transações ativas:", self.lbl_ativas)
        ef.addRow("I/O (páginas):", self.lbl_io)
        raiz.addWidget(est)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        raiz.addWidget(self.log, 1)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self._cancelar)
        botoes.addWidget(self.btn_cancelar)
        self.btn_fechar = QPushButton("Fechar")
        self.btn_fechar.setEnabled(False)
        self.btn_fechar.clicked.connect(self.accept)
        botoes.addWidget(self.btn_fechar)
        raiz.addLayout(botoes)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        raiz.addWidget(self.status)

    def _ligar(self) -> None:
        self._worker.progresso.connect(self._on_progresso)
        self._worker.estatisticas.connect(self._on_stats)
        self._worker.mensagem.connect(self.log.appendPlainText)
        self._worker.terminou.connect(self._on_fim)

    def _tick(self) -> None:
        if self._worker.isRunning():
            self.lbl_tempo.setText(f"{time.monotonic() - self._t0:.1f} s")

    def _on_progresso(self, feito: int, total: int, elapsed: float) -> None:
        if self.barra.maximum() == 0:  # sai do modo indeterminado (pós-backup)
            self.barra.setRange(0, total)
        self.barra.setValue(feito)
        self.lbl_tempo.setText(f"{elapsed:.1f} s")
        taxa = feito / elapsed if elapsed > 0 else 0
        self.lbl_taxa.setText(f"{taxa:.0f} lançamentos/s")
        restantes = total - feito
        if taxa > 0 and restantes > 0:
            self.lbl_eta.setText(f"{restantes / taxa:.0f} s")
        else:
            self.lbl_eta.setText("—")

    def _on_stats(self, s: dict) -> None:
        if any(k in s for k in ("oit", "oat", "ost", "next")):
            self.lbl_trans.setText(
                f"{s.get('oit','—')} / {s.get('oat','—')} / "
                f"{s.get('ost','—')} / {s.get('next','—')}"
            )
        if "ativas" in s:
            self.lbl_ativas.setText(str(s["ativas"]))
        io = s.get("io")
        if isinstance(io, dict) and io:
            partes = []
            for k in ("reads", "writes", "fetches", "marks"):
                if k in io:
                    partes.append(f"{k}={io[k]}")
            self.lbl_io.setText("  ".join(partes) or str(io))

    def _on_fim(self, ok: bool, msg: str) -> None:
        self._timer.stop()
        self.btn_cancelar.setEnabled(False)
        self.btn_fechar.setEnabled(True)
        self.log.appendPlainText(msg)
        self.status.setProperty("role", "ok" if ok else "erro")
        self.status.setText(msg)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _cancelar(self) -> None:
        self.btn_cancelar.setEnabled(False)
        self.log.appendPlainText("Cancelando após o lançamento atual…")
        self._worker.cancelar()

    def reject(self) -> None:
        # fechar pelo X / Esc: cancela e espera a thread encerrar
        if self._worker.isRunning():
            self._worker.cancelar()
            self._worker.wait(5000)
        super().reject()
