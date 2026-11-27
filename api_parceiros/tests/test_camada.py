import os
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "api_parceiros"
# O mesmo padrão do F04-CA10 (grep -rnE … api_parceiros/).
GRAVACAO_DIRETA = re.compile(r"objects\.(create|update|filter\(.*\)\.update)|\.save\(")


def test_api_parceiros_nao_grava_direto_no_banco():
    achados = []
    for arquivo in sorted(PASTA.rglob("*.py")):
        if "tests" in arquivo.relative_to(PASTA).parts:
            continue
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if GRAVACAO_DIRETA.search(linha):
                achados.append(f"{arquivo.relative_to(RAIZ)}:{numero}: {linha.strip()}")
    assert achados == []
    for nome in ("views.py", "serializadores.py", "auth.py"):
        assert "objects." not in (PASTA / nome).read_text(encoding="utf-8")


def test_rajada_api_existe_e_usa_xargs_p_30():
    script = RAIZ / "scripts" / "rajada-api.sh"
    assert script.is_file()
    assert os.access(script, os.X_OK)
    texto = script.read_text(encoding="utf-8")
    assert texto.startswith("#!/usr/bin/env bash")
    assert 'seq "$COMPRAS" | xargs -P 30' in texto and "COMPRAS=30" in texto
    assert "CATRACA_PORTA" in texto and "chave-parceiro-dev" in texto
    assert "rajada-api: OK" in texto and "rajada-api: FALHOU" in texto
    assert not re.search(r"\bjq\b|python", texto, re.IGNORECASE)
