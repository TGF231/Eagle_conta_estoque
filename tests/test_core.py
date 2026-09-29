import pandas as pd
import pytest

from kardex_app.core import (
    FileImportError,
    build_date_str,
    escape_sql_text,
    format_quantidade,
    generate_sql_statements,
    read_table,
    validate_history,
    validate_rows,
)


def make_df(rows):
    return pd.DataFrame(rows, columns=["PRODUTOS_ID", "PRODUTO_NOVA_QUANTIDADE"])


def test_validate_rows_accepts_valid_entries():
    df = make_df([[1, 10], [2, "5,5"]])
    result = validate_rows(df)
    assert not result.has_issues
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]
    assert result.valid_rows[1].quantidade == 5.5


def test_validate_rows_skips_blank_fields_without_aborting():
    df = make_df([[1, 10], [None, None], [2, None], [None, 5], [3, 7]])
    result = validate_rows(df)
    assert [r.produtos_id for r in result.valid_rows] == [1, 3]
    reasons = [i.reason for i in result.issues]
    assert "Linha em branco (ignorada)" in reasons
    assert any("PRODUTO_NOVA_QUANTIDADE não preenchido" in r for r in reasons)
    assert any("PRODUTOS_ID não preenchido" in r for r in reasons)


def test_validate_rows_rejects_invalid_values():
    df = make_df([["abc", 10], [1, "abc"]])
    result = validate_rows(df)
    assert not result.valid_rows
    assert len(result.issues) == 2


def test_validate_rows_rejects_negative_quantity():
    df = make_df([[373, -1], [1, 10]])
    result = validate_rows(df)
    assert [r.produtos_id for r in result.valid_rows] == [1]
    assert len(result.issues) == 1
    assert "negativa" in result.issues[0].reason


def test_validate_rows_requires_columns():
    df = pd.DataFrame({"OUTRA_COLUNA": [1]})
    with pytest.raises(FileImportError):
        validate_rows(df)


def test_format_quantidade():
    assert format_quantidade(10) == "10"
    assert format_quantidade(10.0) == "10"
    assert format_quantidade(5.5) == "5.5"
    assert format_quantidade(1.23456789) == "1.23457"


def test_escape_sql_text_prevents_broken_statements():
    assert escape_sql_text("O'Brien") == "O''Brien"


def test_validate_history():
    assert validate_history("") is not None
    assert validate_history("   ") is not None
    assert validate_history("x" * 201) is not None
    assert validate_history("AJUSTE DE ESTOQUE") is None


def test_generate_sql_statements():
    df = make_df([[1, 10]])
    result = validate_rows(df)
    statements = generate_sql_statements(
        result.valid_rows, "ajuste", "28-SET-2026 10:00:00"
    )
    assert statements == [
        "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'AJUSTE', 10, '28-SET-2026 10:00:00');"
    ]


def test_build_date_str():
    assert build_date_str("28-SET-2026", "10:00:00") == "28-SET-2026 10:00:00"


def test_read_table_csv(tmp_path):
    path = tmp_path / "contagem.csv"
    path.write_text(
        "PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n1;10\n2;5,5\n", encoding="utf-8"
    )
    df = read_table(path)
    result = validate_rows(df)
    assert not result.has_issues
    assert result.valid_rows[1].quantidade == 5.5


def test_read_table_txt_tab_delimited(tmp_path):
    path = tmp_path / "contagem.txt"
    path.write_text(
        "PRODUTOS_ID\tPRODUTO_NOVA_QUANTIDADE\n1\t10\n2\t20\n", encoding="utf-8"
    )
    df = read_table(path)
    result = validate_rows(df)
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]


def test_read_table_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "contagem.pdf"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(FileImportError):
        read_table(path)


def test_read_table_reports_empty_file(tmp_path):
    path = tmp_path / "contagem.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(FileImportError):
        read_table(path)
