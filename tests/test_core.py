import pandas as pd
import pytest

from kardex_app.core import (
    FileImportError,
    build_date_str,
    escape_sql_text,
    format_quantidade,
    generate_sql_statements,
    guess_columns,
    preview_dataframe,
    read_many,
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


def test_generate_sql_statements_escapes_history():
    df = make_df([[1, 10]])
    result = validate_rows(df)
    statements = generate_sql_statements(
        result.valid_rows, "O'Brien", "28-SET-2026 10:00:00"
    )
    assert "'O''BRIEN'" in statements[0]


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
    assert not result.has_issues
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]


def test_read_table_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "contagem.pdf"
    path.write_text("dummy", encoding="utf-8")
    with pytest.raises(FileImportError):
        read_table(path)


def test_read_table_missing_file(tmp_path):
    with pytest.raises(FileImportError):
        read_table(tmp_path / "nao_existe.csv")


def test_validate_rows_with_explicit_mapping():
    df = pd.DataFrame(
        [["x", 1, 10], ["y", 2, "5,5"]],
        columns=["DESCRICAO", "CODIGO", "CONTAGEM"],
    )
    result = validate_rows(df, id_col="CODIGO", qty_col="CONTAGEM")
    assert not result.has_issues
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]
    assert result.valid_rows[1].quantidade == 5.5


def test_validate_rows_without_guessable_columns_raises():
    df = pd.DataFrame({"CODIGO": [1], "CONTAGEM": [10]})
    with pytest.raises(FileImportError):
        validate_rows(df)


def test_validate_rows_rejects_mapping_to_missing_column():
    df = pd.DataFrame({"CODIGO": [1], "CONTAGEM": [10]})
    with pytest.raises(FileImportError):
        validate_rows(df, id_col="CODIGO", qty_col="NAO_EXISTE")


def test_guess_columns_case_and_space_insensitive():
    # guess casa sem diferenciar caso/espaços e devolve o nome ORIGINAL da
    # coluna (tal como veio do arquivo).
    df = pd.DataFrame(columns=[" produtos_id ", "Produto_Nova_Quantidade"])
    id_col, qty_col = guess_columns(df)
    assert id_col == " produtos_id "
    assert qty_col == "Produto_Nova_Quantidade"


def test_guess_columns_returns_none_when_absent():
    df = pd.DataFrame(columns=["CODIGO", "CONTAGEM"])
    assert guess_columns(df) == (None, None)


def test_read_table_without_header_positional_columns(tmp_path):
    path = tmp_path / "sem_cabecalho.csv"
    path.write_text("1;10\n2;20\n", encoding="utf-8")
    df = read_table(path, has_header=False)
    assert list(df.columns) == ["Coluna 1", "Coluna 2"]
    result = validate_rows(df, id_col="Coluna 1", qty_col="Coluna 2")
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]


def test_read_many_concatenates_same_layout(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n1;10\n2;20\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n3;30\n", encoding="utf-8")
    df = read_many([a, b])
    result = validate_rows(df)
    assert [r.produtos_id for r in result.valid_rows] == [1, 2, 3]


def test_read_many_aligns_by_position_with_different_headers(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n1;10\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("COD;QTD\n2;20\n", encoding="utf-8")
    df = read_many([a, b])
    # adota os nomes do primeiro arquivo
    assert list(df.columns) == ["PRODUTOS_ID", "PRODUTO_NOVA_QUANTIDADE"]
    result = validate_rows(df)
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]


def test_read_many_rejects_mismatched_column_count(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n1;10\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE;EXTRA\n2;20;x\n", encoding="utf-8")
    with pytest.raises(FileImportError):
        read_many([a, b])


def test_read_many_empty_list_raises():
    with pytest.raises(FileImportError):
        read_many([])


def test_preview_dataframe_limits_rows_and_blanks_na():
    df = pd.DataFrame(
        {"A": list(range(20)), "B": [None] + list(range(19))}
    )
    headers, rows = preview_dataframe(df, n=5)
    assert headers == ["A", "B"]
    assert len(rows) == 5
    assert rows[0][1] == ""  # None vira string vazia
