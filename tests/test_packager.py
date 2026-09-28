"""Testes do empacotamento .bat/.ps1 com partes e contador de progresso."""
from kardex_app.db import ConexaoConfig
from kardex_app.packager import (
    build_bat,
    build_ps1,
    encoding_para,
    montar_partes,
    write_package,
)


def _cfg(**kw):
    base = dict(
        host="srv", port=3050, database=r"C:\dados\EAGLE.FDB",
        user="SYSDBA", password="masterkey", charset="WIN1252",
    )
    base.update(kw)
    return ConexaoConfig(**base)


def test_build_bat_tem_connstring_driver_e_contador():
    bat = build_bat(_cfg())
    assert "srv/3050:C:\\dados\\EAGLE.FDB" in bat
    assert "isql.exe" in bat
    assert 'for %%f in ("%~dp0parte_*.sql")' in bat  # itera as partes
    assert "[!N!/%TOTAL%]" in bat  # contador de progresso
    assert "-b " in bat  # para no primeiro erro


def test_build_ps1_tem_progresso():
    ps = build_ps1(_cfg(host="localhost"))
    assert "localhost/3050:C:\\dados\\EAGLE.FDB" in ps
    assert "parte_*.sql" in ps
    assert "Write-Progress" in ps


def test_encoding_para():
    assert encoding_para("WIN1252") == "cp1252"
    assert encoding_para("UTF8") == "utf-8"
    assert encoding_para("qualquer") == "cp1252"


def test_montar_partes_recompute_antes_e_depois_com_lotes():
    rec_ids = [1, 2, 3, 4, 5]
    lanc = ["EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'X', 5, 'd');"]
    partes = montar_partes(rec_ids, lanc, lote=2)
    # recompute (5 ids / 2 = 3 lotes) + lançamentos (1 lote) + recompute (3) = 7
    assert len(partes) == 7
    # cada parte termina com COMMIT
    assert all(p.rstrip().endswith("COMMIT;") for p in partes)
    # a parte de lançamentos está no meio (após os 3 lotes de recompute)
    assert "KARDEX_ALTERA_QUANTIDADE" in partes[3]
    # primeira e última são recompute
    assert "KARDEX_RECOMPUTA" in partes[0]
    assert "KARDEX_RECOMPUTA" in partes[-1]


def test_write_package_cria_partes_e_scripts(tmp_path):
    pasta = tmp_path / "saida_pacote"
    lanc = ["EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'X', 5, 'd');"]
    write_package(str(pasta), _cfg(), [1, 2, 3], lanc, lote=2)
    partes = sorted(pasta.glob("parte_*.sql"))
    assert len(partes) >= 3
    assert partes[0].name == "parte_0001.sql"
    assert (pasta / "executar.bat").exists()
    assert (pasta / "executar.ps1").exists()


def test_write_package_limpa_partes_antigas(tmp_path):
    pasta = tmp_path / "p"
    pasta.mkdir()
    (pasta / "parte_9999.sql").write_text("lixo antigo", encoding="cp1252")
    write_package(str(pasta), _cfg(), [1], ["EXECUTE PROCEDURE X(1);"], lote=10)
    assert not (pasta / "parte_9999.sql").exists()
