"""Interface gráfica (PySide6) para importar uma contagem de estoque no KARDEX."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtGui import QIcon
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
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import tema
from .comparacao import ComparacaoDialog
from .conexao import ConexaoDialog
from .core import (
    COLUNA_ARQUIVO,
    HISTORICO_MAX_LEN,
    SOURCE_FILE_FILTER,
    FileImportError,
    aggregate_rows,
    build_date_str,
    build_script,
    comparar_estoque,
    generate_bulk_statements,
    generate_sql_statements,
    generate_zero_statements,
    read_many,
    validate_history,
    validate_rows,
)
from .db import (
    DBError,
    conectar,
    estoque_e_preco_todos,
    estoque_na_data,
    listar_produtos_ativos,
    listar_todos_produtos,
)
from .executor import ExecucaoDialog
from .mapeamento import MapeamentoDialog
from .packager import write_package
from .verificacao import VerificacaoDialog

APP_TITULO = "Eagle Contagem de Estoque"


def recurso(nome: str) -> str:
    """Caminho de um recurso, funcionando tanto no código-fonte quanto no
    executável empacotado pelo PyInstaller (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return str(Path(base) / "assets" / nome)
    return str(Path(__file__).resolve().parent.parent / "assets" / nome)


def app_icon() -> QIcon:
    caminho = recurso("eagle.ico")
    return QIcon(caminho) if Path(caminho).exists() else QIcon()


class KardexWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITULO)
        self.setWindowIcon(app_icon())
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
        self.exec_btn = QPushButton("Executar no banco…")
        self.exec_btn.setEnabled(False)
        self.exec_btn.clicked.connect(self._executar_no_banco)
        map_row.addWidget(self.exec_btn)
        self.conf_btn = QPushButton("Conferir resultado…")
        self.conf_btn.setEnabled(False)
        self.conf_btn.clicked.connect(self._conferir_resultado)
        map_row.addWidget(self.conf_btn)
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

        self.zerar_chk = QCheckBox(
            "Zerar estoque dos itens não contados (consulta o banco ao gerar)"
        )
        raiz.addWidget(self.zerar_chk)

        self.pular_iguais_chk = QCheckBox(
            "Pular itens cujo estoque na data do ajuste já é igual à contagem "
            "(consulta o banco)"
        )
        raiz.addWidget(self.pular_iguais_chk)

        self.lote_chk = QCheckBox(
            "Modo zerar tudo e recontar (inserts em lote, rápido; sequencial)"
        )
        self.lote_chk.setToolTip(
            "Zera o estoque de TODOS os produtos na data (1s antes) e relança a "
            "contagem como entrada. Usa INSERTs brutos + recompute por produto, "
            "em vez da procedure. Roda sequencial (a ordem importa)."
        )
        raiz.addWidget(self.lote_chk)

        self.pacote_chk = QCheckBox(
            "Gerar pacote .bat/.ps1 para rodar direto no isql (mais rápido que "
            "o IBExpert)"
        )
        raiz.addWidget(self.pacote_chk)

        self.backup_chk = QCheckBox(
            "Fazer backup do banco (gbak) antes de executar na interface"
        )
        self.backup_chk.setChecked(True)
        raiz.addWidget(self.backup_chk)

        commit_row = QHBoxLayout()
        commit_row.setContentsMargins(0, 0, 0, 0)
        commit_row.setSpacing(6)
        commit_row.addWidget(QLabel("COMMIT a cada"))
        self.commit_spin = QSpinBox()
        self.commit_spin.setRange(1, 100000)
        self.commit_spin.setValue(200)
        self.commit_spin.setToolTip(
            "Em bases grandes, committar em blocos evita uma transação única "
            "gigante e dá progresso mais frequente no pacote."
        )
        commit_row.addWidget(self.commit_spin)
        commit_row.addWidget(QLabel("registros"))
        commit_row.addSpacing(16)
        commit_row.addWidget(QLabel("Conexões paralelas"))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 32)
        self.workers_spin.setValue(4)
        self.workers_spin.setToolTip(
            "Nº de conexões/transações simultâneas na execução pela interface. "
            "Cada produto é independente, então acelera bastante em bases "
            "grandes."
        )
        commit_row.addWidget(self.workers_spin)
        commit_row.addStretch(1)
        raiz.addLayout(commit_row)

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
        self.exec_btn.setEnabled(False)
        self.conf_btn.setEnabled(False)
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
            self.exec_btn.setEnabled(True)
            self.conf_btn.setEnabled(True)
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
        codigos = []
        origem: dict[str, set[str]] = {}
        tem_origem = COLUNA_ARQUIVO in self._df.columns
        for _, row in self._df.iterrows():
            valor = row[self._id_col]
            if valor is None or str(valor).strip() == "":
                continue
            codigo = str(valor).strip()
            codigos.append(codigo)
            if tem_origem:
                origem.setdefault(codigo, set()).add(str(row[COLUNA_ARQUIVO]))
        if not codigos:
            QMessageBox.information(
                self, "Sem códigos", "Não há códigos para verificar."
            )
            return
        dialog = VerificacaoDialog(codigos, self, self._db_config, origem=origem)
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
        # Formato ISO (YYYY-MM-DD HH:MM:SS): o Firebird interpreta sem depender
        # do idioma/locale da conexão — nomes de mês em português quebravam.
        date_part = self.date_edit.date().toString("yyyy-MM-dd")
        time_part = self.time_edit.time().toString("HH:mm:ss")
        return build_date_str(date_part, time_part)

    def _build_zero_date_str(self) -> str:
        """1 segundo antes da data-base — usado no modo lote para o zeramento
        vir antes da contagem no recompute (sem empate de data/hora)."""
        from PySide6.QtCore import QDateTime

        dt = QDateTime(self.date_edit.date(), self.time_edit.time()).addSecs(-1)
        return dt.toString("yyyy-MM-dd HH:mm:ss")

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
        # une códigos iguais (inclusive com zeros à esquerda) somando a
        # quantidade e ordena os lançamentos por código
        agregadas = sorted(
            aggregate_rows(result.valid_rows), key=lambda r: r.produtos_id
        )

        prep = self._preparar_statements(agregadas, history, date_str)
        if prep is None:
            return  # usuário cancelou a conexão / falha de banco
        statements, info = prep
        if not statements:
            QMessageBox.warning(
                self, "Nada a gerar",
                "Nenhum lançamento restou após os filtros (fora do banco / já "
                "iguais).",
            )
            self._set_status("Nada a gerar.", role="aviso")
            return

        commit_interval = self.commit_spin.value()
        script_content = build_script(statements, commit_interval=commit_interval)
        try:
            Path(sql_path).write_text(script_content, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao salvar SQL", str(exc))
            self._set_status("Falha ao salvar o arquivo SQL.", role="erro")
            return

        pacote_dir = None
        if self.pacote_chk.isChecked():
            base = Path(sql_path).with_suffix("")
            pasta = f"{base}_pacote"
            try:
                pacote_dir = write_package(
                    pasta, self._db_config, statements, lote=commit_interval
                )
            except OSError as exc:
                QMessageBox.critical(self, "Erro ao gerar pacote", str(exc))
                return

        unidas = len(result.valid_rows) - len(agregadas)
        self._set_status(
            self._resumo(info, unidas, len(result.issues), pacote_dir), role="ok"
        )

    def _preparar_statements(self, agregadas, history, date_str,
                             forcar_banco: bool = False):
        """Monta os lançamentos aplicando os filtros que dependem do banco:
        pular códigos fora de PRODUTOS, pular itens cujo estoque na data já bate
        e (se marcado) zerar os não contados. Consulta o banco só quando algum
        desses filtros está ativo (ou `forcar_banco`). Devolve (statements, info)
        ou None se o usuário cancelar / houver erro."""
        if self.lote_chk.isChecked():
            return self._preparar_lote(agregadas, history, date_str)

        precisa = (
            forcar_banco
            or self.zerar_chk.isChecked()
            or self.pacote_chk.isChecked()
            or self.pular_iguais_chk.isChecked()
        )
        existentes = list(agregadas)
        info = {"contados": len(existentes), "fora": 0, "iguais": 0,
                "zerados": 0, "ja_zerados": 0}

        if precisa:
            if self._db_config is None or not self._db_config.database.strip():
                dialog = ConexaoDialog(self, self._db_config)
                if not dialog.exec():
                    QMessageBox.information(
                        self, "Cancelado",
                        "Conexão não informada — nada foi gerado.",
                    )
                    return None
                self._db_config = dialog.config()

            conn = None
            try:
                conn = conectar(self._db_config)
                produtos = set(listar_todos_produtos(conn))

                # pula códigos que não existem em PRODUTOS
                antes = len(existentes)
                existentes = [r for r in existentes if r.produtos_id in produtos]
                info["fora"] = antes - len(existentes)

                # produtos contados (e existentes) — nunca são zerados, mesmo
                # os pulados por já estarem iguais
                contados_ids = {r.produtos_id for r in existentes}

                # pula itens cujo estoque NA DATA (anterior) já bate com a contagem
                if self.pular_iguais_chk.isChecked():
                    est = estoque_na_data(
                        conn, [r.produtos_id for r in existentes], date_str
                    )
                    antes = len(existentes)
                    existentes = [
                        r for r in existentes
                        if round(r.quantidade, 5)
                        != round(est.get(r.produtos_id, 0.0), 5)
                    ]
                    info["iguais"] = antes - len(existentes)

                info["contados"] = len(existentes)
                statements = generate_sql_statements(existentes, history, date_str)

                if self.zerar_chk.isChecked():
                    ativos = listar_produtos_ativos(conn)
                    nao_contados = sorted(ativos - contados_ids)
                    # não zera de novo quem já está zerado na data
                    est_zero = estoque_na_data(conn, nao_contados, date_str)
                    a_zerar = [
                        pid for pid in nao_contados
                        if round(est_zero.get(pid, 0.0), 5) != 0
                    ]
                    info["ja_zerados"] = len(nao_contados) - len(a_zerar)
                    zero = generate_zero_statements(a_zerar, history, date_str)
                    statements += zero
                    info["zerados"] = len(zero)
            except DBError as exc:
                QMessageBox.critical(self, "Erro no banco", str(exc))
                self._set_status("Falha ao consultar o banco.", role="erro")
                return None
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

            return statements, info

        statements = generate_sql_statements(existentes, history, date_str)
        return statements, info

    def _preparar_lote(self, agregadas, history, date_str):
        """Modo lote: zera TODOS os produtos (1s antes da data) e relança a
        contagem, com INSERTs brutos + recompute por produto."""
        if self._db_config is None or not self._db_config.database.strip():
            dialog = ConexaoDialog(self, self._db_config)
            if not dialog.exec():
                QMessageBox.information(
                    self, "Cancelado", "Conexão não informada — nada foi gerado."
                )
                return None
            self._db_config = dialog.config()

        zero_dt = self._build_zero_date_str()
        conn = None
        try:
            conn = conectar(self._db_config)
            produtos = set(listar_todos_produtos(conn))
            dados = estoque_e_preco_todos(conn, zero_dt)
        except DBError as exc:
            QMessageBox.critical(self, "Erro no banco", str(exc))
            self._set_status("Falha ao consultar o banco.", role="erro")
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        existentes = [r for r in agregadas if r.produtos_id in produtos]
        fora = len(agregadas) - len(existentes)
        contagem = {r.produtos_id: r.quantidade for r in existentes}
        estoque = {pid: v[0] for pid, v in dados.items()}
        preco = {pid: v[1] for pid, v in dados.items()}

        stmts, binfo = generate_bulk_statements(
            contagem, estoque, preco, history, date_str, zero_dt
        )
        info = {
            "contados": binfo["contados"],
            "fora": fora,
            "iguais": 0,
            "zerados": binfo["zerados"],
            "ja_zerados": 0,
            "lote": True,
        }
        return stmts, info

    @staticmethod
    def _resumo(info: dict, unidas: int, issues: int, pacote_dir=None) -> str:
        msg = f"OK: {info['contados']} produto(s) contado(s)."
        if unidas > 0:
            msg += f" {unidas} linha(s) unida(s) por código repetido."
        if info.get("zerados"):
            msg += f" {info['zerados']} item(ns) zerado(s)."
        if info.get("iguais"):
            msg += f" {info['iguais']} já igual(is) pulado(s)."
        if info.get("ja_zerados"):
            msg += f" {info['ja_zerados']} já zerado(s) ignorado(s)."
        if info.get("fora"):
            msg += f" {info['fora']} fora do banco pulado(s)."
        if issues:
            msg += f" {issues} linha(s) ignorada(s)."
        if pacote_dir:
            msg += f" Pacote em: {pacote_dir}"
        return msg

    def _conferir_resultado(self) -> None:
        """Compara a contagem com o PRODUTO_ESTOQUE_DISPONIVEL atual da tabela
        PRODUTOS e lista as divergências (conferência pós-ajuste)."""
        if self._df is None or not (self._id_col and self._qty_col):
            return
        try:
            result = validate_rows(self._df, self._id_col, self._qty_col)
        except FileImportError as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            return
        if not result.valid_rows:
            QMessageBox.warning(self, "Sem dados", "Nenhuma linha válida.")
            return
        agregadas = sorted(
            aggregate_rows(result.valid_rows), key=lambda r: r.produtos_id
        )
        date_str = self._build_date_str()

        if self._db_config is None or not self._db_config.database.strip():
            dialog = ConexaoDialog(self, self._db_config)
            if not dialog.exec():
                return
            self._db_config = dialog.config()

        conn = None
        try:
            conn = conectar(self._db_config)
            # estoque NA DATA da contagem (inclui o lançamento feito nessa data),
            # não o estoque atual — movimentos posteriores não interferem
            est = estoque_na_data(
                conn, [r.produtos_id for r in agregadas], date_str,
                inclusive=True,
            )
        except DBError as exc:
            QMessageBox.critical(self, "Erro no banco", str(exc))
            return
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        # produto sem movimento até a data = estoque 0 naquele momento
        disp = {r.produtos_id: est.get(r.produtos_id, 0.0) for r in agregadas}
        comp = comparar_estoque(agregadas, disp)
        ComparacaoDialog(comp, self).exec()
        self._set_status(
            f"Conferência: {len(comp.iguais)} OK, {len(comp.divergentes)} "
            f"divergente(s), {len(comp.ausentes)} ausente(s).",
            role="erro" if comp.divergentes else "ok",
        )

    def _executar_no_banco(self) -> None:
        """Executa os lançamentos direto no banco (via fdb), com barra de
        progresso, tempo e estatísticas — sem gerar .bat/.ps1."""
        if self._df is None or not (self._id_col and self._qty_col):
            return
        history = self.history_edit.text()
        erro = validate_history(history)
        if erro:
            QMessageBox.critical(self, "Erro", erro)
            return
        try:
            result = validate_rows(self._df, self._id_col, self._qty_col)
        except FileImportError as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            return
        if not result.valid_rows:
            QMessageBox.warning(self, "Sem dados", "Nenhuma linha válida.")
            return

        date_str = self._build_date_str()
        agregadas = sorted(
            aggregate_rows(result.valid_rows), key=lambda r: r.produtos_id
        )

        # força a consulta ao banco para filtrar códigos fora de PRODUTOS
        # (senão a procedure abortaria) e aplicar os demais filtros marcados
        prep = self._preparar_statements(
            agregadas, history, date_str, forcar_banco=True
        )
        if prep is None:
            return
        statements, info = prep
        if not statements:
            QMessageBox.warning(
                self, "Nada a executar",
                "Nenhum lançamento restou após os filtros.",
            )
            return

        resumo = self._resumo(info, len(result.valid_rows) - len(agregadas), 0)
        resp = QMessageBox.question(
            self,
            "Executar no banco",
            f"Isto vai ALTERAR o estoque no banco:\n{self._db_config.database}\n\n"
            f"{len(statements)} lançamento(s).\n{resumo}\n\n"
            "Recomenda-se um backup antes. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        backup_path = None
        if self.backup_chk.isChecked():
            base = Path(self._db_config.database).stem or "banco"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            sugestao = f"{base}_{ts}.fbk"
            backup_path, _ = QFileDialog.getSaveFileName(
                self, "Salvar backup (gbak)", sugestao,
                "Backup Firebird (*.fbk);;Todos os arquivos (*)",
            )
            if not backup_path:
                return  # cancelou o backup → não executa
            if not backup_path.lower().endswith(".fbk"):
                backup_path += ".fbk"

        # o modo lote roda sequencial (a ordem zero→contagem→recompute importa)
        n_workers = 1 if self.lote_chk.isChecked() else self.workers_spin.value()
        ExecucaoDialog(
            self._db_config, statements, self.commit_spin.value(),
            backup_path, n_workers, self
        ).exec()
        self._set_status(f"Execução no banco: {resumo}", role="ok")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITULO)
    app.setWindowIcon(app_icon())
    tema.definir_escuro(False)
    app.setStyleSheet(tema.folha_estilo())
    window = KardexWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
