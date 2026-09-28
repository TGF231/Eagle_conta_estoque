# -*- coding: utf-8 -*-
"""Diálogo para conectar a um Firebird 2.5 e verificar os códigos da contagem
contra PRODUTOS / PRODUTOSREFERENCIAS."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .db import CHARSETS, ConexaoConfig, DBError, conectar, verificar_codigos


class VerificacaoDialog(QDialog):
    def __init__(self, codigos, parent=None, config: ConexaoConfig | None = None):
        super().__init__(parent)
        self.setWindowTitle("Verificar códigos no banco (Firebird 2.5)")
        self.resize(640, 560)
        self._codigos = list(codigos)
        self._config = config or ConexaoConfig()
        self._build_ui()

    def config(self) -> ConexaoConfig:
        """Configuração atual (para o chamador reaproveitar entre aberturas)."""
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
        raiz.setSpacing(12)

        titulo = QLabel("Verificar códigos no banco")
        titulo.setProperty("role", "titulo")
        raiz.addWidget(titulo)

        info = QLabel(
            f"{len(self._codigos)} código(s) distinto(s) serão conferidos "
            "contra PRODUTOS (PRODUTOS_ID) e PRODUTOSREFERENCIAS "
            "(PRODUTO_REFERENCIA)."
        )
        info.setProperty("role", "dica")
        info.setWordWrap(True)
        raiz.addWidget(info)

        conexao = QGroupBox("Conexão")
        form = QFormLayout(conexao)
        form.setContentsMargins(12, 8, 12, 12)
        form.setSpacing(8)

        self.host_edit = QLineEdit(self._config.host)
        form.addRow("Servidor:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self._config.port)
        form.addRow("Porta:", self.port_spin)

        self.db_edit = QLineEdit(self._config.database)
        self.db_edit.setPlaceholderText(r"C:\caminho\BANCO.FDB ou alias")
        form.addRow("Banco (arquivo/alias):", self.db_edit)

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
        raiz.addWidget(conexao)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.verificar_btn = QPushButton("Verificar")
        self.verificar_btn.setProperty("role", "accent")
        self.verificar_btn.clicked.connect(self._executar)
        botoes.addWidget(self.verificar_btn)
        fechar_btn = QPushButton("Fechar")
        fechar_btn.clicked.connect(self.accept)
        botoes.addWidget(fechar_btn)
        raiz.addLayout(botoes)

        rot = QLabel("RESULTADO")
        rot.setProperty("role", "secao")
        raiz.addWidget(rot)
        self.saida = QPlainTextEdit()
        self.saida.setReadOnly(True)
        self.saida.setPlaceholderText("Clique em Verificar para conferir os códigos.")
        raiz.addWidget(self.saida, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        raiz.addWidget(self.status)

    def _set_status(self, texto: str, role: str) -> None:
        self.status.setProperty("role", role)
        self.status.setText(texto)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _executar(self) -> None:
        self.saida.clear()
        self._set_status("Conectando…", role="dica")
        self.verificar_btn.setEnabled(False)
        conn = None
        try:
            conn = conectar(self.config())
            resultado = verificar_codigos(conn, self._codigos)
        except DBError as exc:
            self._set_status(str(exc), role="erro")
            self.verificar_btn.setEnabled(True)
            return
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        self.verificar_btn.setEnabled(True)
        self._mostrar(resultado)

    def _mostrar(self, r) -> None:
        linhas = [
            f"Total conferido: {r.total}",
            f"Encontrados: {r.encontrados}   "
            f"(produtos: {len(r.em_produtos)}, referências: {len(r.em_referencias)})",
            f"Ausentes: {len(r.ausentes)}",
            "",
        ]
        if r.em_referencias:
            linhas.append("Códigos resolvidos por referência (código → PRODUTOS_ID):")
            for ref, pid in sorted(r.em_referencias.items()):
                linhas.append(f"  {ref} → {pid}")
            linhas.append("")
        if r.ausentes:
            linhas.append("Códigos NÃO encontrados:")
            linhas.extend(f"  {c}" for c in r.ausentes)
        else:
            linhas.append("Todos os códigos foram encontrados.")

        self.saida.setPlainText("\n".join(linhas))
        if r.ausentes:
            self._set_status(
                f"{len(r.ausentes)} código(s) sem correspondência no banco.",
                role="aviso",
            )
        else:
            self._set_status("Todos os códigos batem com o banco.", role="ok")
