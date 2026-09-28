"""Diálogo de verificação/mapeamento das colunas do arquivo de contagem.

Como a ferramenta aceita xlsx/xls/csv/txt de origens variadas, o nome e a
posição das colunas mudam de arquivo para arquivo. Esta tela mostra uma prévia
do que foi lido e deixa o usuário apontar qual coluna é o produto e qual é a
nova quantidade — os seletores já vêm pré-preenchidos quando os nomes batem
com o esperado.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .core import colunas_visiveis, guess_columns, preview_dataframe


class MapeamentoDialog(QDialog):
    PREVIEW_LINHAS = 15

    def __init__(self, df: pd.DataFrame, nome_arquivo: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verificar colunas do arquivo")
        self.resize(720, 520)
        self._headers = colunas_visiveis(df)
        self._id_col: Optional[str] = None
        self._qty_col: Optional[str] = None
        self._build_ui(df, nome_arquivo)

    def _build_ui(self, df: pd.DataFrame, nome_arquivo: str) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 14, 16, 14)
        raiz.setSpacing(12)

        titulo = QLabel("Verificar colunas do arquivo")
        titulo.setProperty("role", "titulo")
        raiz.addWidget(titulo)

        info = QLabel(
            (f"Arquivo: {nome_arquivo}\n" if nome_arquivo else "")
            + f"{len(self._headers)} coluna(s), {len(df)} linha(s). "
            "Indique abaixo qual coluna contém o código do produto e qual "
            "contém a nova quantidade contada."
        )
        info.setProperty("role", "dica")
        info.setWordWrap(True)
        raiz.addWidget(info)

        # ---------------------------------------------------- mapeamento
        grupo = QGroupBox("Mapeamento das colunas")
        form = QFormLayout(grupo)
        form.setContentsMargins(12, 8, 12, 12)
        form.setSpacing(8)

        self.combo_id = QComboBox()
        self.combo_qty = QComboBox()
        for combo in (self.combo_id, self.combo_qty):
            combo.addItem("— selecione —", userData=None)
            for header in self._headers:
                combo.addItem(header, userData=header)
            combo.currentIndexChanged.connect(self._atualizar_estado)

        form.addRow("Coluna do produto (PRODUTOS_ID):", self.combo_id)
        form.addRow("Coluna da nova quantidade:", self.combo_qty)
        raiz.addWidget(grupo)

        # pré-seleção pelos nomes esperados
        g_id, g_qty = guess_columns(df)
        if g_id in self._headers:
            self.combo_id.setCurrentIndex(self._headers.index(g_id) + 1)
        if g_qty in self._headers:
            self.combo_qty.setCurrentIndex(self._headers.index(g_qty) + 1)

        # -------------------------------------------------------- prévia
        raiz.addWidget(self._rotulo_secao("PRÉVIA DO ARQUIVO"))
        self.tabela = QTableWidget()
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.tabela.setAlternatingRowColors(True)
        self._preencher_previa(df)
        raiz.addWidget(self.tabela, 1)

        self.aviso = QLabel("")
        self.aviso.setProperty("role", "aviso")
        self.aviso.setWordWrap(True)
        raiz.addWidget(self.aviso)

        # -------------------------------------------------------- botões
        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Confirmar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.button(QDialogButtonBox.StandardButton.Ok).setProperty(
            "role", "accent"
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        self._botoes = botoes
        raiz.addWidget(botoes)

        self._atualizar_estado()

    @staticmethod
    def _rotulo_secao(texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setProperty("role", "secao")
        return lbl

    def _preencher_previa(self, df: pd.DataFrame) -> None:
        headers, rows = preview_dataframe(df, self.PREVIEW_LINHAS)
        self.tabela.setColumnCount(len(headers))
        self.tabela.setHorizontalHeaderLabels(headers)
        self.tabela.setRowCount(len(rows))
        for i, linha in enumerate(rows):
            for j, valor in enumerate(linha):
                self.tabela.setItem(i, j, QTableWidgetItem(valor))
        self.tabela.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.tabela.resizeColumnsToContents()

    def _atualizar_estado(self) -> None:
        self._id_col = self.combo_id.currentData()
        self._qty_col = self.combo_qty.currentData()
        ok_btn = self._botoes.button(QDialogButtonBox.StandardButton.Ok)

        if self._id_col is None or self._qty_col is None:
            self.aviso.setText("Selecione as duas colunas para continuar.")
            ok_btn.setEnabled(False)
        elif self._id_col == self._qty_col:
            self.aviso.setText(
                "Produto e quantidade não podem ser a mesma coluna."
            )
            ok_btn.setEnabled(False)
        else:
            self.aviso.setText("")
            ok_btn.setEnabled(True)

    def mapeamento(self) -> tuple[Optional[str], Optional[str]]:
        return self._id_col, self._qty_col
