# -*- coding: utf-8 -*-
"""Diálogo de conferência: compara a contagem com o PRODUTO_ESTOQUE_DISPONIVEL
atual da tabela PRODUTOS e lista as divergências."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import tema
from .core import ComparacaoResultado, format_quantidade


class ComparacaoDialog(QDialog):
    def __init__(self, resultado: ComparacaoResultado, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conferir resultado (estoque disponível)")
        self.resize(680, 560)
        self._r = resultado
        self._build_ui()
        self._preencher()

    def _build_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 14, 16, 14)
        raiz.setSpacing(12)

        titulo = QLabel("Conferir resultado")
        titulo.setProperty("role", "titulo")
        raiz.addWidget(titulo)

        self.resumo = QLabel("")
        self.resumo.setWordWrap(True)
        raiz.addWidget(self.resumo)

        self.so_diverg = QCheckBox("Mostrar apenas divergências")
        self.so_diverg.setChecked(True)
        self.so_diverg.toggled.connect(self._preencher)
        raiz.addWidget(self.so_diverg)

        self.tabela = QTableWidget()
        self.tabela.setColumnCount(5)
        self.tabela.setHorizontalHeaderLabels(
            ["Produto", "Contado", "Estoque na data", "Diferença", "Status"]
        )
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        raiz.addWidget(self.tabela, 1)

        botoes = QHBoxLayout()
        self.btn_copiar = QPushButton("Copiar diferenças")
        self.btn_copiar.clicked.connect(self._copiar_diferencas)
        botoes.addWidget(self.btn_copiar)
        botoes.addStretch(1)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        botoes.addWidget(fechar)
        raiz.addLayout(botoes)

    def _copiar_diferencas(self) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        linhas = ["PRODUTO\tCONTADO\tESTOQUE_NA_DATA\tDIFERENCA"]
        for pid, contado, disp in self._r.divergentes:
            linhas.append(
                f"{pid}\t{format_quantidade(contado)}\t"
                f"{format_quantidade(disp)}\t{format_quantidade(contado - disp)}"
            )
        QApplication.clipboard().setText("\n".join(linhas))
        self.btn_copiar.setText("Copiado!")
        QTimer.singleShot(
            1500, lambda: self.btn_copiar.setText("Copiar diferenças")
        )

    def _preencher(self) -> None:
        r = self._r
        pal = tema.atual()
        so_div = self.so_diverg.isChecked()

        linhas = []
        for pid, contado, disp in r.divergentes:
            linhas.append((pid, contado, disp, "Divergente", pal.bad))
        if not so_div:
            for pid, val in r.iguais:
                linhas.append((pid, val, val, "OK", pal.ok))
        for pid in r.ausentes:
            linhas.append((pid, None, None, "Produto ausente", pal.warn))

        self.tabela.setRowCount(len(linhas))
        for i, (pid, contado, disp, status, cor) in enumerate(linhas):
            dif = ""
            if contado is not None and disp is not None:
                dif = format_quantidade(contado - disp)
            valores = [
                str(pid),
                format_quantidade(contado) if contado is not None else "—",
                format_quantidade(disp) if disp is not None else "—",
                dif,
                status,
            ]
            for j, v in enumerate(valores):
                item = QTableWidgetItem(v)
                if j in (1, 2, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if j == 4:
                    item.setForeground(QColor(cor))
                self.tabela.setItem(i, j, item)
        self.tabela.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.resumo.setProperty(
            "role", "erro" if r.divergentes else "ok"
        )
        self.resumo.setText(
            f"Conferidos: {r.total}   ·   OK: {len(r.iguais)}   ·   "
            f"Divergentes: {len(r.divergentes)}   ·   "
            f"Ausentes: {len(r.ausentes)}"
        )
        self.resumo.style().unpolish(self.resumo)
        self.resumo.style().polish(self.resumo)
