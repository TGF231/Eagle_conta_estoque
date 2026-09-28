"""Interface gráfica (PySide6) para importar uma contagem de estoque no KARDEX."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import tema
from .core import (
    HISTORICO_MAX_LEN,
    PT_MONTHS,
    SOURCE_FILE_FILTER,
    FileImportError,
    build_date_str,
    generate_sql_statements,
    read_many,
    validate_history,
    validate_rows,
    write_sql_file,
)
from .mapeamento import MapeamentoDialog
from .verificacao import VerificacaoDialog

APP_TITULO = "Importa KARDEX"


class KardexWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITULO)
        self.resize(760, 640)
        self._df = None
        self._id_col = None
        self._qty_col = None
        self._paths: list[str] = []
        self._db_config = None
        self._build_ui()

    def _build_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 16, 18, 16)
        raiz.setSpacing(12)

        # ------------------------------------------------------------ topo
        topo = QHBoxLayout()
        titulo = QLabel(APP_TITULO)
        titulo.setProperty("role", "titulo")
        topo.addWidget(titulo)
        topo.addStretch(1)
        self.tema_btn = QPushButton("Tema escuro")
        self.tema_btn.clicked.connect(self._alternar_tema)
        topo.addWidget(self.tema_btn)
        raiz.addLayout(topo)

        subtitulo = QLabel(
            "Gera o SQL de ajuste de estoque (KARDEX_ALTERA_QUANTIDADE) a "
            "partir de uma contagem em Excel, CSV ou TXT."
        )
        subtitulo.setProperty("role", "dica")
        subtitulo.setWordWrap(True)
        raiz.addWidget(subtitulo)

        # -------------------------------------------------------- arquivos
        files_group = QGroupBox("Arquivos")
        files_form = QFormLayout(files_group)
        files_form.setContentsMargins(12, 8, 12, 12)
        files_form.setSpacing(8)

        self.source_edit = QLineEdit()
        self.source_edit.setReadOnly(True)
        self.source_edit.setPlaceholderText(
            "Selecione uma ou mais planilhas de contagem…"
        )
        files_form.addRow(
            "Arquivos de contagem:",
            self._path_row(self.source_edit, self._select_source, "Selecionar…"),
        )

        self.chk_sem_cabecalho = QCheckBox(
            "Os arquivos não têm linha de cabeçalho (colunas por posição)"
        )
        self.chk_sem_cabecalho.toggled.connect(self._recarregar)
        files_form.addRow("", self.chk_sem_cabecalho)

        self.sql_edit = QLineEdit()
        self.sql_edit.setPlaceholderText("Onde salvar o script .sql…")
        files_form.addRow(
            "Salvar SQL em:", self._path_row(self.sql_edit, self._select_sql)
        )

        map_row = QHBoxLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(6)
        self.map_label = QLabel("Nenhum arquivo carregado.")
        self.map_label.setProperty("role", "dica")
        self.map_label.setWordWrap(True)
        map_row.addWidget(self.map_label, 1)
        self.map_btn = QPushButton("Verificar colunas…")
        self.map_btn.setEnabled(False)
        self.map_btn.clicked.connect(self._verificar_colunas)
        map_row.addWidget(self.map_btn)
        self.db_btn = QPushButton("Verificar no banco…")
        self.db_btn.setEnabled(False)
        self.db_btn.clicked.connect(self._verificar_no_banco)
        map_row.addWidget(self.db_btn)
        map_container = QWidget()
        map_container.setLayout(map_row)
        files_form.addRow("Colunas:", map_container)
        raiz.addWidget(files_group)

        # ------------------------------------------------- dados do lançamento
        details_group = QGroupBox("Dados do lançamento")
        details_form = QFormLayout(details_group)
        details_form.setContentsMargins(12, 8, 12, 12)
        details_form.setSpacing(8)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        details_form.addRow("Data de inserção:", self.date_edit)

        self.time_edit = QTimeEdit(QTime.currentTime())
        self.time_edit.setDisplayFormat("HH:mm:ss")
        details_form.addRow("Hora de inserção:", self.time_edit)

        self.history_edit = QLineEdit("AJUSTE DE ESTOQUE")
        self.history_edit.setMaxLength(HISTORICO_MAX_LEN)
        details_form.addRow("Texto histórico:", self.history_edit)
        raiz.addWidget(details_group)

        # ------------------------------------------------------------ ação
        acao = QHBoxLayout()
        acao.addStretch(1)
        self.generate_btn = QPushButton("Gerar SQL")
        self.generate_btn.setProperty("role", "accent")
        self.generate_btn.clicked.connect(self._generate_sql)
        acao.addWidget(self.generate_btn)
        raiz.addLayout(acao)

        # ------------------------------------------------------------- log
        log_label = QLabel("LINHAS IGNORADAS NA ÚLTIMA GERAÇÃO")
        log_label.setProperty("role", "secao")
        raiz.addWidget(log_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Nenhuma linha ignorada ainda.")
        raiz.addWidget(self.log, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        raiz.addWidget(self.status_label)

    @staticmethod
    def _path_row(line_edit: QLineEdit, on_select, texto: str = "Selecionar…") -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(line_edit, 1)
        button = QPushButton(texto)
        button.clicked.connect(on_select)
        row.addWidget(button)
        return container

    def _alternar_tema(self) -> None:
        tema.definir_escuro(not tema.e_escuro())
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(tema.folha_estilo())
        self.tema_btn.setText("Tema claro" if tema.e_escuro() else "Tema escuro")

    def _select_source(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Selecione os arquivos de contagem", "", SOURCE_FILE_FILTER
        )
        if paths:
            self._paths = list(paths)
            self._atualizar_resumo_arquivos()
            self._carregar_arquivos(abrir_mapeamento=True)

    def _atualizar_resumo_arquivos(self) -> None:
        if not self._paths:
            self.source_edit.setText("")
            return
        nomes = [Path(p).name for p in self._paths]
        if len(nomes) == 1:
            self.source_edit.setText(nomes[0])
        else:
            self.source_edit.setText(
                f"{len(nomes)} arquivos: " + ", ".join(nomes)
            )

    def _recarregar(self) -> None:
        """Rele os arquivos (ex.: ao alternar 'sem cabeçalho')."""
        if self._paths:
            self._carregar_arquivos(abrir_mapeamento=True)

    def _carregar_arquivos(self, abrir_mapeamento: bool) -> None:
        """Lê e unifica os arquivos; opcionalmente abre a verificação."""
        self._df = None
        self._id_col = None
        self._qty_col = None
        self.map_btn.setEnabled(False)
        self.db_btn.setEnabled(False)
        try:
            self._df = read_many(
                self._paths, has_header=not self.chk_sem_cabecalho.isChecked()
            )
        except FileImportError as exc:
            self.map_label.setText(f"Falha ao ler: {exc}")
            self.map_label.setProperty("role", "erro")
            self._repolir(self.map_label)
            return
        self.map_btn.setEnabled(True)
        if abrir_mapeamento:
            self._verificar_colunas()

    def _verificar_colunas(self) -> None:
        if self._df is None:
            return
        if len(self._paths) == 1:
            titulo = Path(self._paths[0]).name
        else:
            titulo = f"{len(self._paths)} arquivos unificados"
        dialog = MapeamentoDialog(self._df, titulo, self)
        if dialog.exec():
            self._id_col, self._qty_col = dialog.mapeamento()
            self.map_label.setText(
                f"Produto → “{self._id_col}”   ·   "
                f"Quantidade → “{self._qty_col}”"
            )
            self.map_label.setProperty("role", "ok")
            self.db_btn.setEnabled(True)
        else:
            if not (self._id_col and self._qty_col):
                self.map_label.setText(
                    "Colunas ainda não confirmadas — clique em "
                    "“Verificar colunas…”."
                )
                self.map_label.setProperty("role", "aviso")
        self._repolir(self.map_label)

    def _verificar_no_banco(self) -> None:
        if self._df is None or not self._id_col:
            return
        codigos = [
            v
            for v in self._df[self._id_col].tolist()
            if v is not None and str(v).strip() != ""
        ]
        if not codigos:
            QMessageBox.information(
                self, "Sem códigos", "Não há códigos para verificar."
            )
            return
        dialog = VerificacaoDialog(codigos, self, self._db_config)
        dialog.exec()
        # guarda a config para reaproveitar na próxima abertura (sem a senha
        # persistir em disco — fica só em memória nesta sessão)
        self._db_config = dialog.config()

    @staticmethod
    def _repolir(widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _select_sql(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar como", "", "SQL (*.sql);;Todos os arquivos (*)"
        )
        if path:
            if not path.lower().endswith(".sql"):
                path += ".sql"
            self.sql_edit.setText(path)

    def _set_status(self, text: str, role: str) -> None:
        self.status_label.setProperty("role", role)
        self.status_label.setText(text)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _build_date_str(self) -> str:
        qdate = self.date_edit.date()
        month = PT_MONTHS[qdate.month()]
        date_part = f"{qdate.day():02d}-{month}-{qdate.year()}"
        time_part = self.time_edit.time().toString("HH:mm:ss")
        return build_date_str(date_part, time_part)

    def _generate_sql(self) -> None:
        self.log.clear()

        sql_path = self.sql_edit.text().strip()
        history = self.history_edit.text()

        if not self._paths or self._df is None:
            QMessageBox.critical(
                self, "Erro", "Selecione ao menos um arquivo de contagem válido."
            )
            return
        if not sql_path:
            QMessageBox.critical(self, "Erro", "Defina o caminho de saída do SQL.")
            return
        if not (self._id_col and self._qty_col):
            QMessageBox.warning(
                self,
                "Colunas não confirmadas",
                "Confirme quais colunas são o produto e a quantidade na tela "
                "de verificação antes de gerar o SQL.",
            )
            self._verificar_colunas()
            if not (self._id_col and self._qty_col):
                return

        history_error = validate_history(history)
        if history_error:
            QMessageBox.critical(self, "Erro", history_error)
            return

        try:
            result = validate_rows(self._df, self._id_col, self._qty_col)
        except FileImportError as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            self._set_status("Falha na validação.", role="erro")
            return

        if result.issues:
            self.log.setPlainText(
                "\n".join(
                    f"Linha {issue.row_number}: {issue.reason}"
                    for issue in result.issues
                )
            )

        if not result.valid_rows:
            QMessageBox.warning(
                self,
                "Nenhuma linha válida",
                "Nenhuma linha válida foi encontrada para gerar SQL.",
            )
            self._set_status("Nenhuma linha válida.", role="aviso")
            return

        date_str = self._build_date_str()
        statements = generate_sql_statements(result.valid_rows, history, date_str)

        try:
            write_sql_file(statements, sql_path)
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao salvar SQL", str(exc))
            self._set_status("Falha ao salvar o arquivo SQL.", role="erro")
            return

        msg = f"SQL gerado com sucesso: {len(statements)} lançamento(s)."
        if result.issues:
            msg += f" {len(result.issues)} linha(s) ignorada(s)."
        self._set_status(msg, role="ok")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITULO)
    tema.definir_escuro(False)
    app.setStyleSheet(tema.folha_estilo())
    window = KardexWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
