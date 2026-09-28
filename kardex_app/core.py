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
    """Só remove espaços em volta do nome das colunas — preserva o texto
    original (e o caso) para que a tela de mapeamento mostre o cabeçalho tal
    como veio do arquivo."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _norm(name) -> str:
    return str(name).strip().upper()


def guess_columns(df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    """Tenta adivinhar as colunas de ID e quantidade pelos nomes esperados
    (comparação sem diferenciar maiúsculas/espaços). Devolve (id, qty) com
    None onde não houver correspondência."""
    por_nome = {_norm(c): c for c in df.columns}
    id_col = por_nome.get(_norm(REQUIRED_COLUMNS[0]))
    qty_col = por_nome.get(_norm(REQUIRED_COLUMNS[1]))
    return id_col, qty_col


def preview_dataframe(
    df: pd.DataFrame, n: int = 15
) -> tuple[list[str], list[list[str]]]:
    """Cabeçalhos e as primeiras `n` linhas (como texto), para a prévia da tela
    de mapeamento."""
    headers = [str(c) for c in df.columns]
    rows: list[list[str]] = []
    for _, row in df.head(n).iterrows():
        rows.append(["" if _is_blank(v) else str(v) for v in row.tolist()])
    return headers, rows


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _to_float(value) -> Optional[float]:
    """Aceita '1234,56' (pt-BR), '1234.56' e espaços/aspas acidentais."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip().strip("'\"")
    if text == "":
        return None
    text = text.replace(" ", "")
    if "," in text and "." in text:
        # Ambos presentes: vírgula é separador de milhar, ponto é decimal.
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value) -> Optional[int]:
    as_float = _to_float(value)
    if as_float is None:
        return None
    if not as_float.is_integer():
        return None
    return int(as_float)


def _read_delimited(path: Path, has_header: bool) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    first_line = lines[0] if lines else ""
    try:
        dialect = csv.Sniffer().sniff(first_line, delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if ";" in first_line else ("\t" if "\t" in first_line else ",")
    header = 0 if has_header else None
    return pd.read_csv(
        path, sep=delimiter, dtype=str, header=header, encoding="utf-8-sig"
    )


def _colunas_posicionais(n: int) -> list[str]:
    return [f"Coluna {i + 1}" for i in range(n)]


def read_table(path: Union[str, Path], has_header: bool = True) -> pd.DataFrame:
    """Lê o arquivo de contagem (xlsx/xlsm/xls/csv/txt) e normaliza colunas.

    Com `has_header=False`, a primeira linha é tratada como dado e as colunas
    recebem nomes posicionais (``Coluna 1``, ``Coluna 2``…) — para arquivos que
    não trazem cabeçalho."""
    path = Path(path)
    if not path.is_file():
        raise FileImportError(f"Arquivo não encontrado: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise FileImportError(
            f"Extensão não suportada: '{suffix}'. Suportados: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )

    header = 0 if has_header else None
    try:
        if suffix in (".xlsx", ".xlsm"):
            df = pd.read_excel(path, engine="openpyxl", dtype=str, header=header)
        elif suffix == ".xls":
            df = pd.read_excel(path, engine="xlrd", dtype=str, header=header)
        else:
            df = _read_delimited(path, has_header)
    except FileImportError:
        raise
    except Exception as exc:  # arquivo corrompido, engine ausente, etc.
        raise FileImportError(f"Falha ao ler '{path.name}': {exc}") from exc

    if df.empty:
        raise FileImportError("Arquivo não contém dados.")

    if not has_header:
        df = df.copy()
        df.columns = _colunas_posicionais(len(df.columns))

    return _normalize_columns(df)


def read_many(
    paths: "list[Union[str, Path]]", has_header: bool = True
) -> pd.DataFrame:
    """Lê e concatena vários arquivos num único DataFrame.

    Os arquivos precisam ter o mesmo número de colunas; a concatenação é feita
    **por posição**, adotando os nomes de coluna do primeiro arquivo (assim,
    layouts iguais com cabeçalhos ligeiramente diferentes ainda unificam)."""
    if not paths:
        raise FileImportError("Nenhum arquivo selecionado.")

    frames = []
    base_cols: Optional[list[str]] = None
    for p in paths:
        nome = Path(p).name
        df = read_table(p, has_header=has_header)
        if base_cols is None:
            base_cols = list(df.columns)
        elif len(df.columns) != len(base_cols):
            raise FileImportError(
                f"'{nome}' tem {len(df.columns)} coluna(s), mas o primeiro "
                f"arquivo tem {len(base_cols)}. Todos os arquivos precisam ter "
                "o mesmo layout para serem unificados."
            )
        else:
            df = df.copy()
            df.columns = base_cols
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def validate_rows(
    df: pd.DataFrame,
    id_col: Optional[str] = None,
    qty_col: Optional[str] = None,
) -> ImportResult:
    """Valida linha a linha; nunca aborta no primeiro campo vazio/inválido —
    cada linha problemática vira um RowIssue e as demais continuam sendo
    processadas.

    `id_col`/`qty_col` dizem quais colunas do arquivo correspondem ao
    PRODUTOS_ID e à nova quantidade. Quando omitidos, tenta adivinhar pelos
    nomes esperados; se não conseguir, levanta FileImportError."""
    df = _normalize_columns(df)

    if id_col is None or qty_col is None:
        g_id, g_qty = guess_columns(df)
        id_col = id_col or g_id
        qty_col = qty_col or g_qty
    if id_col is None or qty_col is None:
        raise FileImportError(
            "Não foi possível identificar as colunas de produto e quantidade. "
            "Use a tela de mapeamento para indicá-las."
        )
    faltando = [c for c in (id_col, qty_col) if c not in df.columns]
    if faltando:
        raise FileImportError(
            "Colunas mapeadas não existem no arquivo: " + ", ".join(faltando)
        )

    result = ImportResult()
    for idx, row in df.iterrows():
        row_number = idx + 2  # cabeçalho ocupa a linha 1
        raw_id = row.get(id_col)
        raw_qty = row.get(qty_col)

        id_blank = _is_blank(raw_id)
        qty_blank = _is_blank(raw_qty)

        if id_blank and qty_blank:
            result.issues.append(
                RowIssue(row_number, "Linha em branco (ignorada)", raw_id, raw_qty)
            )
            continue
        if id_blank:
            result.issues.append(
                RowIssue(row_number, "PRODUTOS_ID não preenchido", raw_id, raw_qty)
            )
            continue
        if qty_blank:
            result.issues.append(
                RowIssue(
                    row_number,
                    "PRODUTO_NOVA_QUANTIDADE não preenchido",
                    raw_id,
                    raw_qty,
                )
            )
            continue

        produtos_id = _to_int(raw_id)
        if produtos_id is None:
            result.issues.append(
                RowIssue(
                    row_number, f"PRODUTOS_ID inválido: {raw_id!r}", raw_id, raw_qty
                )
            )
            continue

        quantidade = _to_float(raw_qty)
        if quantidade is None:
            result.issues.append(
                RowIssue(
                    row_number,
                    f"PRODUTO_NOVA_QUANTIDADE inválida: {raw_qty!r}",
                    raw_id,
                    raw_qty,
                )
            )
            continue

        result.valid_rows.append(ParsedRow(row_number, produtos_id, quantidade))

    return result


def format_quantidade(value: Union[int, float]) -> str:
    """Formata a quantidade com até 5 casas decimais (NUMERIC(14,5)), sem
    zeros/ponto decimal supérfluos."""
    quantized = round(float(value), QUANTIDADE_SCALE)
    text = f"{quantized:.{QUANTIDADE_SCALE}f}"
    text = text.rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def escape_sql_text(text: str) -> str:
    """Evita SQL quebrado/injeção quando o texto contém apóstrofo."""
    return text.replace("'", "''")


def validate_history(history: str) -> Optional[str]:
    if history is None or history.strip() == "":
        return "Informe o texto histórico."
    if len(history) > HISTORICO_MAX_LEN:
        return f"Texto histórico excede o limite de {HISTORICO_MAX_LEN} caracteres."
    return None


def build_date_str(date_str: str, time_str: str) -> str:
    return f"{date_str} {time_str}"


def generate_sql_statements(
    rows: list[ParsedRow], history: str, date_str: str
) -> list[str]:
    escaped_history = escape_sql_text(history.strip().upper())
    statements = []
    for row in rows:
        quantidade_str = format_quantidade(row.quantidade)
        statements.append(
            "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE("
            f"{row.produtos_id}, '{escaped_history}', {quantidade_str}, "
            f"'{date_str}');"
        )
    return statements


def write_sql_file(statements: list[str], path: Union[str, Path]) -> None:
    path = Path(path)
    content = "\n".join(statements)
    if statements:
        content += "\n"
    path.write_text(content, encoding="utf-8")
