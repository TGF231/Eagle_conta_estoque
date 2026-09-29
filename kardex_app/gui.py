"""Interface gráfica (PySide6) para importar uma contagem de estoque no KARDEX."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QApplication,
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

from .core import (
    HISTORICO_MAX_LEN,
    PT_MONTHS,
    SOURCE_FILE_FILTER,
    FileImportError,
    build_date_str,
    generate_sql_statements,
    read_table,
    validate_history,
    validate_rows,
    write_sql_file,
)


class KardexWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Importa KARDEX")
        self.resize(700, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        files_group = QGroupBox("Arquivos")
        files_form = QFormLayout(files_group)

        self.source_edit = QLineEdit()
        files_form.addRow("Arquivo de contagem:", self._path_row(self.source_edit, self._select_source))

        self.sql_edit = QLineEdit()
        files_form.addRow("Salvar SQL em:", self._path_row(self.sql_edit, self._select_sql))

        layout.addWidget(files_group)

        details_group = QGroupBox("Dados do lançamento")
        details_form = QFormLayout(details_group)

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

        layout.addWidget(details_group)

        self.generate_btn = QPushButton("Gerar SQL")
        self.generate_btn.clicked.connect(self._generate_sql)
        layout.addWidget(self.generate_btn)

        layout.addWidget(QLabel("Linhas ignoradas na última geração:"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    @staticmethod
    def _path_row(line_edit: QLineEdit, on_select) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(line_edit)
        button = QPushButton("Selecionar...")
        button.clicked.connect(on_select)
        row.addWidget(button)
        return row

    def _select_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecione o arquivo de contagem", "", SOURCE_FILE_FILTER
        )
        if path:
            self.source_edit.setText(path)

    def _select_sql(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar como", "", "SQL (*.sql);;Todos os arquivos (*)"
        )
        if path:
            if not path.lower().endswith(".sql"):
                path += ".sql"
            self.sql_edit.setText(path)

    def _set_status(self, text: str, ok: bool) -> None:
        self.status_label.setStyleSheet(f"color: {'green' if ok else 'red'};")
        self.status_label.setText(text)

    def _generate_sql(self) -> None:
        self.log.clear()

        source_path = self.source_edit.text().strip()
        sql_path = self.sql_edit.text().strip()
        history = self.history_edit.text()

        if not source_path or not Path(source_path).is_file():
            QMessageBox.critical(self, "Erro", "Selecione um arquivo de contagem válido.")
            return
        if not sql_path:
            QMessageBox.critical(self, "Erro", "Defina o caminho de saída do SQL.")
            return

        history_error = validate_history(history)
        if history_error:
            QMessageBox.critical(self, "Erro", history_error)
            return

        try:
            df = read_table(source_path)
        except FileImportError as exc:
            QMessageBox.critical(self, "Erro ao ler arquivo", str(exc))
            self._set_status("Falha na leitura do arquivo.", ok=False)
            return

        try:
            result = validate_rows(df)
        except FileImportError as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            self._set_status("Falha na validação.", ok=False)
            return

        if not result.valid_rows:
            QMessageBox.critical(self, "Erro", "Nenhuma linha válida encontrada no arquivo.")
            self._set_status("Nenhuma linha válida encontrada.", ok=False)
            return

        date = self.date_edit.date()
        time_str = self.time_edit.time().toString("HH:mm:ss")
        date_str = build_date_str(
            f"{date.day():02d}-{PT_MONTHS[date.month()]}-{date.year()}", time_str
        )

        statements = generate_sql_statements(result.valid_rows, history, date_str)

        try:
            write_sql_file(sql_path, statements)
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao gerar SQL", str(exc))
            self._set_status("Falha na geração.", ok=False)
            return

        if result.has_issues:
            self.log.setPlainText(
                "\n".join(f"Linha {i.row_number}: {i.reason}" for i in result.issues)
            )
            self._set_status(
                f"SQL gerado com {len(result.valid_rows)} lançamento(s); "
                f"{len(result.issues)} linha(s) ignorada(s) (veja a lista acima).",
                ok=True,
            )
        else:
            self._set_status(
                f"SQL gerado com sucesso! ({len(result.valid_rows)} lançamento(s))", ok=True
            )


def main() -> None:
    app = QApplication(sys.argv)
    window = KardexWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
