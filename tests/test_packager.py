"""Testes do empacotamento .bat/.ps1 para rodar via isql."""
from kardex_app.db import ConexaoConfig
from kardex_app.packager import (
    SCRIPT_NAME,
    build_bat,
    build_ps1,
    encoding_para,
    write_package,
)


def _cfg(**kw):
    base = dict(
        host="srv", port=3050, database=r"C:\dados\EAGLE.FDB",
        user="SYSDBA", password="masterkey", charset="WIN1252",
    )
    base.update(kw)
    return ConexaoConfig(**base)


def test_build_bat_tem_connstring_e_chama_isql():
    bat = build_bat(_cfg())
    assert "srv/3050:C:\\dados\\EAGLE.FDB" in bat
    assert "isql.exe" in bat
    assert f'-i "%~dp0{SCRIPT_NAME}"' in bat
    assert "-ch %CS%" in bat
    assert "-b " in bat  # para no primeiro erro


def test_build_ps1_tem_connstring_e_isql():
    ps = build_ps1(_cfg(host="localhost"))
    assert "localhost/3050:C:\\dados\\EAGLE.FDB" in ps
    assert "isql.exe" in ps
    assert SCRIPT_NAME in ps


def test_encoding_para():
    assert encoding_para("WIN1252") == "cp1252"
    assert encoding_para("UTF8") == "utf-8"
    assert encoding_para("qualquer") == "cp1252"


def test_write_package_cria_tres_arquivos(tmp_path):
    pasta = tmp_path / "saida_pacote"
    conteudo = "EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'X', 5, 'd');\n"
    write_package(str(pasta), conteudo, _cfg())
    assert (pasta / SCRIPT_NAME).exists()
    assert (pasta / "executar.bat").exists()
    assert (pasta / "executar.ps1").exists()
    # script gravado na codificação do charset (cp1252 p/ WIN1252)
    assert (pasta / SCRIPT_NAME).read_text(encoding="cp1252") == conteudo


def test_write_package_script_utf8_quando_charset_utf8(tmp_path):
    pasta = tmp_path / "p2"
    conteudo = "EXECUTE PROCEDURE X(1, 'AÇÃO', 5, 'd');\n"
    write_package(str(pasta), conteudo, _cfg(charset="UTF8"))
    assert (pasta / SCRIPT_NAME).read_text(encoding="utf-8") == conteudo
