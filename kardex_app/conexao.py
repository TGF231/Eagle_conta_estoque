# -*- coding: utf-8 -*-
"""Diálogo simples de conexão ao Firebird, reutilizável fora da verificação
(ex.: para zerar itens não contados ao gerar o SQL principal)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .db import CHARSETS, ConexaoConfig


class ConexaoDialog(QDialog):
    def __init__(self, parent=None, config: ConexaoConfig | None = None):
        super().__init__(parent)
        self.setWindowTitle("Conexão com o banco (Firebird 2.5)")
        self.resize(520, 260)
        self._config = config or ConexaoConfig()
        self._build_ui()

    def config(self) -> ConexaoConfig:
        return ConexaoConfig(
            host=self.host_edit.text().strip() or "localhost",
            port=self.port_spin.value(),
            database=self.db_edit.text().strip(),
            user=self.user_edit.text().strip() or "SYSDBA",
            password=self.pwd_edit.text(),
            charset=self.charset_combo.currentText(),
        )

    def _build_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 14, 16, 14)
        raiz.setSpacing(10)

        info = QLabel(
            "Informe a conexão para consultar os produtos ativos e zerar os "
            "que não estão na contagem."
        )
        info.setProperty("role", "dica")
        info.setWordWrap(True)
        raiz.addWidget(info)

        form = QFormLayout()
        form.setSpacing(8)

        self.host_edit = QLineEdit(self._config.host)
        form.addRow("Servidor:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self._config.port)
        form.addRow("Porta:", self.port_spin)

        self.db_edit = QLineEdit(self._config.database)
        self.db_edit.setPlaceholderText(r"C:\caminho\BANCO.FDB ou alias")
        db_row = QWidget()
        db_lay = QHBoxLayout(db_row)
        db_lay.setContentsMargins(0, 0, 0, 0)
        db_lay.setSpacing(6)
        db_lay.addWidget(self.db_edit, 1)
        db_btn = QPushButton("Selecionar…")
        db_btn.clicked.connect(self._selecionar_banco)
        db_lay.addWidget(db_btn)
        form.addRow("Banco (arquivo/alias):", db_row)

        self.user_edit = QLineEdit(self._config.user)
        form.addRow("Usuário:", self.user_edit)

        self.pwd_edit = QLineEdit(self._config.password)
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Senha:", self.pwd_edit)

        self.charset_combo = QComboBox()
        self.charset_combo.addItems(CHARSETS)
        if self._config.charset in CHARSETS:
            self.charset_combo.setCurrentText(self._config.charset)
        form.addRow("Charset:", self.charset_combo)
        raiz.addLayout(form)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Conectar")
        botoes.button(QDialogButtonBox.StandardButton.Ok).setProperty(
            "role", "accent"
        )
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        raiz.addWidget(botoes)

    def _selecionar_banco(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o banco de dados Firebird",
            "",
            "Banco Firebird (*.fdb *.gdb *.ib);;Todos os arquivos (*)",
        )
        if path:
            self.db_edit.setText(path)
