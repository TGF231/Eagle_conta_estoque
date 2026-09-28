"""Testes da classificação de códigos (verificar_codigos) com um fake de
conexão no padrão DB-API — sem Firebird de verdade."""
import pytest

from kardex_app.db import DBError, verificar_codigos


class FakeCursor:
    def __init__(self, produtos, referencias):
        self._produtos = set(produtos)  # ints existentes em PRODUTOS
        self._referencias = dict(referencias)  # ref(str) -> produtos_id(int)
        self._resultado = []

    def execute(self, sql, params):
        if "FROM PRODUTOS " in sql or sql.strip().startswith(
            "SELECT PRODUTOS_ID FROM PRODUTOS"
        ):
            self._resultado = [
                (int(p),) for p in params if int(p) in self._produtos
            ]
        elif "PRODUTOSREFERENCIAS" in sql:
            self._resultado = [
                (ref, self._referencias[ref])
                for ref in params
                if ref in self._referencias
            ]
        else:
            self._resultado = []

    def fetchall(self):
        return self._resultado


class FakeConn:
    def __init__(self, produtos, referencias):
        self._cur = FakeCursor(produtos, referencias)

    def cursor(self):
        return self._cur


class ExplodingCursor:
    def execute(self, sql, params):
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
