import pandas as pd
import pytest

from kardex_app.core import (
    COLUNA_ARQUIVO,
    FileImportError,
    aggregate_rows,
    build_date_str,
    colunas_visiveis,
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
        result.valid_rows, "ajuste", "2026-09-28 10:00:00"
    )
    assert statements == [
        "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'AJUSTE', 10, '2026-09-28 10:00:00');"
    ]


def test_generate_sql_statements_escapes_history():
    df = make_df([[1, 10]])
    result = validate_rows(df)
    statements = generate_sql_statements(
        result.valid_rows, "O'Brien", "2026-09-28 10:00:00"
    )
    assert "'O''BRIEN'" in statements[0]


def test_build_date_str():
    assert build_date_str("2026-09-28", "10:00:00") == "2026-09-28 10:00:00"


def test_aggregate_rows_soma_codigos_iguais_com_zeros_a_esquerda():
    # "007", "7" e "0007" caem no id 7 → somam; ordem de 1ª aparição preservada
    df = pd.DataFrame(
        [["007", 10], ["3", 2], ["7", 5], ["0007", 1], ["3", 8]],
        columns=["PRODUTOS_ID", "PRODUTO_NOVA_QUANTIDADE"],
    )
    result = validate_rows(df)
    agg = aggregate_rows(result.valid_rows)
    assert [(r.produtos_id, r.quantidade) for r in agg] == [(7, 16.0), (3, 10.0)]


def test_aggregate_rows_sem_duplicados_mantem_tudo():
    df = pd.DataFrame(
        [[1, 10], [2, 20]],
        columns=["PRODUTOS_ID", "PRODUTO_NOVA_QUANTIDADE"],
    )
    result = validate_rows(df)
    agg = aggregate_rows(result.valid_rows)
    assert [(r.produtos_id, r.quantidade) for r in agg] == [(1, 10.0), (2, 20.0)]


def test_build_script_envolve_com_recomputa_antes_e_depois():
    from kardex_app.core import RECOMPUTA_DATA, build_script

    stmts = ["EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'X', 5, '2026-01-01 00:00:00');"]
    script = build_script(stmts)
    # dois blocos de recompute (antes e depois)
    assert script.count("KARDEX_RECOMPUTA(:PRODUTOS_ID") == 2
    assert script.count("EXECUTE BLOCK") == 2
    assert RECOMPUTA_DATA in script
    # o lançamento fica entre os dois recomputes
    i1 = script.find("KARDEX_RECOMPUTA")
    ialt = script.find("KARDEX_ALTERA_QUANTIDADE")
    i2 = script.rfind("KARDEX_RECOMPUTA")
    assert i1 < ialt < i2
    # terminadores para o EXECUTE BLOCK rodar em isql/IBExpert
    assert "SET TERM ^ ;" in script and "SET TERM ; ^" in script


def test_build_script_sem_recomputa():
    from kardex_app.core import build_script

    stmts = ["EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'X', 5, 'd');"]
    script = build_script(stmts, com_recomputa=False)
    assert "KARDEX_RECOMPUTA" not in script
    assert script.strip() == stmts[0]


def test_generate_zero_statements():
    from kardex_app.core import generate_zero_statements

    stmts = generate_zero_statements([10, 22], "ajuste", "2026-09-28 10:00:00")
    assert stmts == [
        "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(10, 'AJUSTE', 0, '2026-09-28 10:00:00');",
        "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(22, 'AJUSTE', 0, '2026-09-28 10:00:00');",
    ]


def test_generate_zero_statements_escapes_history():
    from kardex_app.core import generate_zero_statements

    stmts = generate_zero_statements([1], "O'Brien", "2026-09-28 10:00:00")
    assert "'O''BRIEN'" in stmts[0]
    assert ", 0, " in stmts[0]


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
    # adota os nomes do primeiro arquivo (colunas internas à parte)
    assert colunas_visiveis(df) == ["PRODUTOS_ID", "PRODUTO_NOVA_QUANTIDADE"]
    result = validate_rows(df)
    assert [r.produtos_id for r in result.valid_rows] == [1, 2]


def test_read_many_registra_proveniencia(tmp_path):
    a = tmp_path / "loja1.csv"
    a.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n1;10\n", encoding="utf-8")
    b = tmp_path / "loja2.csv"
    b.write_text("PRODUTOS_ID;PRODUTO_NOVA_QUANTIDADE\n2;20\n", encoding="utf-8")
    df = read_many([a, b])
    assert COLUNA_ARQUIVO in df.columns
    assert COLUNA_ARQUIVO not in colunas_visiveis(df)
    assert list(df[COLUNA_ARQUIVO]) == ["loja1.csv", "loja2.csv"]
    # a prévia não expõe a coluna interna
    headers, _ = preview_dataframe(df)
    assert COLUNA_ARQUIVO not in headers


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
