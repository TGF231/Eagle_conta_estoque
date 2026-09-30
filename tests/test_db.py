"""Testes da classificação de códigos (verificar_codigos) com um fake de
conexão no padrão DB-API — sem Firebird de verdade."""
import pytest

from kardex_app.db import DBError, listar_produtos_ativos, verificar_codigos


class FakeCursor:
    def __init__(self, produtos, referencias, ativos=None):
        self._produtos = set(produtos)  # ints existentes em PRODUTOS
        self._referencias = dict(referencias)  # ref(str) -> produtos_id(int)
        self._ativos = set(ativos) if ativos is not None else set(produtos)
        self._resultado = []

    def execute(self, sql, params=None):
        if "PRODUTO_INATIVO" in sql:
            self._resultado = [(p,) for p in sorted(self._ativos)]
        elif "PRODUTOSREFERENCIAS" in sql:
            self._resultado = [
                (ref, self._referencias[ref])
                for ref in (params or [])
                if ref in self._referencias
            ]
        elif "FROM PRODUTOS" in sql:
            self._resultado = [
                (int(p),) for p in (params or []) if int(p) in self._produtos
            ]
        else:
            self._resultado = []

    def fetchall(self):
        return self._resultado


class FakeConn:
    def __init__(self, produtos, referencias, ativos=None):
        self._cur = FakeCursor(produtos, referencias, ativos)

    def cursor(self):
        return self._cur


class ExplodingCursor:
    def execute(self, sql, params=None):
        raise RuntimeError("boom")

    def fetchall(self):
        return []


class ExplodingConn:
    def cursor(self):
        return ExplodingCursor()


def test_codigo_encontrado_em_produtos():
    conn = FakeConn(produtos={1, 2, 3}, referencias={})
    r = verificar_codigos(conn, ["1", "2", "9"])
    assert r.em_produtos == {"1", "2"}
    assert r.ausentes == ["9"]
    assert r.encontrados == 2


def test_zeros_a_esquerda_casam_com_produto():
    # "007" e "0010" devem casar com os produtos 7 e 10, preservando o texto
    conn = FakeConn(produtos={7, 10}, referencias={})
    r = verificar_codigos(conn, ["007", "0010", "008"])
    assert r.em_produtos == {"007", "0010"}
    assert r.ausentes == ["008"]


def test_codigo_encontrado_em_referencias_resolve_produtos_id():
    conn = FakeConn(produtos={10}, referencias={"7891234567895": 55})
    r = verificar_codigos(conn, ["10", "7891234567895", "0000"])
    assert r.em_produtos == {"10"}
    assert r.em_referencias == {"7891234567895": 55}
    assert r.ausentes == ["0000"]


def test_produto_tem_prioridade_sobre_referencia():
    # "10" existe como produto; não deve nem ir para o lote de referências
    conn = FakeConn(produtos={10}, referencias={"10": 99})
    r = verificar_codigos(conn, ["10"])
    assert r.em_produtos == {"10"}
    assert "10" not in r.em_referencias


def test_codigos_nao_inteiros_so_batem_como_referencia():
    conn = FakeConn(produtos={1}, referencias={"ABC-1": 42})
    r = verificar_codigos(conn, ["ABC-1", "1"])
    assert r.em_produtos == {"1"}
    assert r.em_referencias == {"ABC-1": 42}
    assert r.ausentes == []


def test_normaliza_duplicados_e_vazios():
    conn = FakeConn(produtos={1}, referencias={})
    r = verificar_codigos(conn, ["1", "1", " 1 ", None, "", "2"])
    assert r.total == 2  # "1" e "2" (após trim/dedup)
    assert r.em_produtos == {"1"}
    assert r.ausentes == ["2"]


def test_lista_vazia():
    conn = FakeConn(produtos={1}, referencias={})
    r = verificar_codigos(conn, [])
    assert r.total == 0
    assert r.encontrados == 0
    assert r.ausentes == []


def test_erro_de_consulta_vira_dberror():
    with pytest.raises(DBError):
        verificar_codigos(ExplodingConn(), ["1"])


def test_tipos_sem_estoque_constante():
    from kardex_app.db import TIPOS_SEM_ESTOQUE

    # 07 = uso/consumo, 08 = ativo imobilizado
    assert TIPOS_SEM_ESTOQUE == {7, 8}


def test_sql_delete_lancamento_escapa_aspas():
    from kardex_app.db import sql_delete_lancamento

    sql = sql_delete_lancamento("2026-09-30 10:00:00", "O'BRIEN")
    assert "KARDEX_DATA_HORA = '2026-09-30 10:00:00'" in sql
    assert "'O''BRIEN'" in sql


def test_listar_produtos_ativos():
    conn = FakeConn(produtos={1, 2, 3}, referencias={}, ativos={1, 3})
    assert listar_produtos_ativos(conn) == {1, 3}


def test_listar_produtos_ativos_erro_vira_dberror():
    with pytest.raises(DBError):
        listar_produtos_ativos(ExplodingConn())
