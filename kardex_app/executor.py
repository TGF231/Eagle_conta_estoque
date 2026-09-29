# -*- coding: utf-8 -*-
"""Execução dos lançamentos direto no banco (via fdb), numa thread, com barra de
progresso, tempo, throughput e estatísticas de transação/servidor.

Alternativa ao pacote .bat/.ps1: em vez de gerar scripts, roda aqui e o usuário
acompanha o andamento em tempo real."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
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
                 n_workers: int = 4, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._stmts = statements
        self._commit = max(1, int(commit_interval or 1))
        self._backup_path = backup_path
        self._n_workers = max(1, int(n_workers or 1))
        self._cancelar = False
        self._feito = 0
        self._erro = None
        self._lock = threading.Lock()

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

    def _rodar_particao(self, stmts: list[str]) -> None:
        """Executado numa thread própria, com sua própria conexão/transação.
        Cada produto é independente (linhas distintas no KARDEX), então
        partições diferentes não conflitam."""
        con = None
        try:
            con = conectar(self._cfg)
            cur = con.cursor()
            n = 0
            for sql in stmts:
                if self._cancelar or self._erro:
                    con.rollback()
                    return
                cur.execute(sql)
                n += 1
                with self._lock:
                    self._feito += 1
                if n % self._commit == 0:
                    con.commit()
            con.commit()
        except Exception as exc:
            with self._lock:
                if self._erro is None:
                    self._erro = f"Erro na execução: {exc}"
            if con is not None:
                try:
                    con.rollback()
                except Exception:
                    pass
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass

    def run(self) -> None:
        total = len(self._stmts)
        t0 = time.monotonic()
        if not self._fazer_backup():
            return
        if total == 0:
            self.terminou.emit(True, "Nada a executar.")
            return

        # particiona round-robin (ordem é irrelevante); nº de workers limitado
        # ao total de lançamentos
        n = min(self._n_workers, total)
        particoes = [self._stmts[i::n] for i in range(n)]
        self.mensagem.emit(
            f"Executando {total} lançamento(s) em {n} conexão(ões) paralela(s)…"
        )

        threads = [
            threading.Thread(target=self._rodar_particao, args=(p,), daemon=True)
            for p in particoes
        ]
        for t in threads:
            t.start()

        stats_con = None
        try:
            stats_con = conectar(self._cfg)
        except Exception:
            stats_con = None

        while any(t.is_alive() for t in threads):
            time.sleep(0.3)
            with self._lock:
                feito = self._feito
            self.progresso.emit(feito, total, time.monotonic() - t0)
            if stats_con is not None:
                self.estatisticas.emit(_coletar_stats(stats_con))

        for t in threads:
            t.join()
        if stats_con is not None:
            try:
                self.estatisticas.emit(_coletar_stats(stats_con))
                stats_con.close()
            except Exception:
                pass

        elapsed = time.monotonic() - t0
        if self._erro is not None:
            self.terminou.emit(
                False, f"{self._erro} (partições sem commit sofreram rollback)."
            )
        elif self._cancelar:
            self.terminou.emit(
                False,
                f"Cancelado após {self._feito} de {total} "
                "(partições sem commit sofreram rollback).",
            )
        else:
            self.progresso.emit(total, total, elapsed)
            self.terminou.emit(
                True, f"Concluído: {total} lançamento(s) em {elapsed:.1f}s "
                f"({n} conexões)."
            )


class ExecucaoDialog(QDialog):
    def __init__(self, cfg: ConexaoConfig, statements: list[str],
                 commit_interval: int, backup_path: str | None = None,
                 n_workers: int = 4, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Executar no banco")
        self.resize(620, 560)
        self._total = len(statements)
        self._t0 = time.monotonic()
        self._worker = ExecucaoWorker(
            cfg, statements, commit_interval, backup_path, n_workers, self
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
