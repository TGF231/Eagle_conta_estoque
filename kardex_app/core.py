"""Lógica de negócio (sem dependência de GUI) para importar uma contagem de
estoque e gerar comandos SQL que chamam a procedure KARDEX_ALTERA_QUANTIDADE.

A procedure é responsável por inserir o lançamento no KARDEX e por refletir o
efeito no apuramento de CMV (KARDEX_CMV_MPM); este módulo só monta a chamada.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import pandas as pd

PT_MONTHS = {
    1: "JAN",
    2: "FEV",
    3: "MAR",
    4: "ABR",
    5: "MAI",
    6: "JUN",
    7: "JUL",
    8: "AGO",
    9: "SET",
    10: "OUT",
    11: "NOV",
    12: "DEZ",
}

REQUIRED_COLUMNS = ("PRODUTOS_ID", "PRODUTO_NOVA_QUANTIDADE")

# KARDEX.KARDEX_HISTORICO é VARCHAR(200) (ver ddl/KARDEX.json).
HISTORICO_MAX_LEN = 200

# KARDEX.KARDEX_QUANTIDADE / KARDEX_CMV_MPM.QUANTIDADE_OPERACAO são
# NUMERIC(14,5) (ver ddl/KARDEX.json e ddl/KARDEX_CMV_MPM.json).
QUANTIDADE_PRECISION = 14
QUANTIDADE_SCALE = 5

SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv", ".txt"}

SOURCE_FILE_FILTER = (
    "Arquivos suportados (*.xlsx *.xlsm *.xls *.csv *.txt);;"
    "Excel (*.xlsx *.xlsm *.xls);;CSV (*.csv);;Texto (*.txt);;Todos os arquivos (*)"
)


class FileImportError(Exception):
    """Erro ao ler ou interpretar o arquivo de contagem."""


@dataclass
class RowIssue:
    row_number: int  # número da linha na planilha/arquivo (cabeçalho = linha 1)
    reason: str
    raw_produtos_id: object = None
    raw_quantidade: object = None


@dataclass
class ParsedRow:
    row_number: int
    produtos_id: int
    quantidade: float


@dataclass
class ImportResult:
    valid_rows: list[ParsedRow] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def _to_float(value) -> Optional[float]:
    """Aceita '1234,56' (pt-BR), '1234.56' e espaços/aspas acidentais."""
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip().strip("'\"")
    if not text:
        return None
    # Formato pt-BR "1.234,56" ou "1234,56" -> "1234.56"
    if "," in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value) -> Optional[int]:
    number = _to_float(value)
    if number is None or not float(number).is_integer():
        return None
    return int(number)


def read_table(path: Union[str, Path]) -> pd.DataFrame:
    """Lê xlsx/xlsm/xls/csv/txt em um DataFrame com colunas normalizadas.

    Levanta FileImportError com mensagem amigável em caso de falha.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise FileImportError(
            f"Formato não suportado: '{ext or path.name}'. "
            "Use um arquivo .xlsx, .xls, .csv ou .txt."
        )

    try:
        if ext in (".xlsx", ".xlsm"):
            df = pd.read_excel(path, engine="openpyxl")
        elif ext == ".xls":
            df = pd.read_excel(path, engine="xlrd")
        else:
            df = _read_delimited(path)
    except FileImportError:
        raise
    except Exception as exc:  # erros de engine, encoding, arquivo corrompido, etc.
        raise FileImportError(f"Não foi possível ler o arquivo: {exc}") from exc

    return _normalize_columns(df)


def _read_delimited(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(4096)
    if not sample.strip():
        raise FileImportError("O arquivo está vazio.")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        sep = dialect.delimiter
    except csv.Error:
        sep = ";" if sample.count(";") >= sample.count(",") else ","
    return pd.read_csv(path, sep=sep, engine="python", encoding="utf-8-sig")


def validate_rows(df: pd.DataFrame) -> ImportResult:
    """Valida cada linha e separa lançamentos válidos de linhas com problema
    (campos não preenchidos, valores inválidos etc.) em vez de abortar tudo
    na primeira falha.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise FileImportError(
            "Coluna(s) obrigatória(s) ausente(s) no arquivo: " + ", ".join(missing)
        )

    result = ImportResult()
    for pos, row in df.iterrows():
        row_number = pos + 2  # linha 1 é o cabeçalho
        raw_id = row["PRODUTOS_ID"]
        raw_qty = row["PRODUTO_NOVA_QUANTIDADE"]

        id_blank = _is_blank(raw_id)
        qty_blank = _is_blank(raw_qty)

        if id_blank and qty_blank:
            result.issues.append(RowIssue(row_number, "Linha em branco (ignorada)"))
            continue
        if id_blank:
            result.issues.append(
                RowIssue(row_number, "PRODUTOS_ID não preenchido", raw_id, raw_qty)
            )
            continue
        if qty_blank:
            result.issues.append(
                RowIssue(
                    row_number, "PRODUTO_NOVA_QUANTIDADE não preenchido", raw_id, raw_qty
                )
            )
            continue

        produtos_id = _to_int(raw_id)
        if produtos_id is None:
            result.issues.append(
                RowIssue(row_number, f"PRODUTOS_ID inválido: {raw_id!r}", raw_id, raw_qty)
            )
            continue

        quantidade = _to_float(raw_qty)
        if quantidade is None:
            result.issues.append(
                RowIssue(row_number, f"Quantidade inválida: {raw_qty!r}", raw_id, raw_qty)
            )
            continue

        if quantidade < 0:
            # Uma contagem de estoque é sempre um valor absoluto; um valor
            # negativo aqui vira um delta de SAÍDA na procedure e pode
            # estourar em "estoque negativo" bem depois, já com o lote
            # parcialmente aplicado no banco. Rejeitamos antes de gerar o SQL.
            result.issues.append(
                RowIssue(
                    row_number,
                    f"Quantidade negativa: {raw_qty!r} (uma contagem de estoque não pode ser negativa)",
                    raw_id,
                    raw_qty,
                )
            )
            continue

        quantidade = round(quantidade, QUANTIDADE_SCALE)
        limit = 10 ** (QUANTIDADE_PRECISION - QUANTIDADE_SCALE)
        if abs(quantidade) >= limit:
            result.issues.append(
                RowIssue(
                    row_number,
                    f"Quantidade fora do intervalo suportado (NUMERIC({QUANTIDADE_PRECISION},"
                    f"{QUANTIDADE_SCALE})): {quantidade}",
                    raw_id,
                    raw_qty,
                )
            )
            continue

        result.valid_rows.append(ParsedRow(row_number, produtos_id, quantidade))

    return result


def validate_history(history: str) -> Optional[str]:
    text = history.strip()
    if not text:
        return "O texto histórico não pode ficar em branco."
    if len(text) > HISTORICO_MAX_LEN:
        return (
            f"O texto histórico excede {HISTORICO_MAX_LEN} caracteres "
            f"(atual: {len(text)})."
        )
    return None


def format_quantidade(quantidade: float) -> str:
    if float(quantidade).is_integer():
        return str(int(quantidade))
    text = f"{quantidade:.{QUANTIDADE_SCALE}f}".rstrip("0").rstrip(".")
    return text


def escape_sql_text(text: str) -> str:
    return text.replace("'", "''")


def build_date_str(date_part: str, time_part: str) -> str:
    return f"{date_part} {time_part}"


def generate_sql_statements(
    rows: list[ParsedRow], history: str, date_str: str
) -> list[str]:
    history_sql = escape_sql_text(history.strip().upper())
    statements = []
    for row in rows:
        qty_fmt = format_quantidade(row.quantidade)
        statements.append(
            "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE"
            f"({row.produtos_id}, '{history_sql}', {qty_fmt}, '{date_str}');"
        )
    return statements


def write_sql_file(path: Union[str, Path], statements: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for statement in statements:
            fh.write(statement + "\n")
