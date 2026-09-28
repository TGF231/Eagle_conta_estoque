# Eagle — Contagem de Estoque Externa

Ferramenta com interface gráfica (PySide6) para importar uma contagem de estoque
e gerar um script SQL de ajuste. Cada linha da contagem vira uma chamada
`EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(...)`, que grava o lançamento na
tabela `KARDEX` e, pela própria procedure, reflete o efeito no apuramento de CMV
(`KARDEX_CMV_MPM`).

## Requisitos

- Python 3.10+
- Dependências em `requirements.txt` (PySide6, pandas, openpyxl, xlrd, fdb)
- Para a verificação no banco: driver `fdb` **e** a biblioteca cliente do
  Firebird (`fbclient.dll`) acessível. O restante do app funciona sem eles.

## Instalação 

### Execução Padrão ↓

 - Faça o download da última versão na aba de Releases e rode o executável (Sem instalação nem configuração necessários.)

### Execução de desenvolvimento ↓ 

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

# Como Usar

```bash
python main.py
```
OU
```
Eagle_Contagem_de_Estoque.exe
```

Na janela:

1. **Arquivos de contagem** — selecione **um ou mais** arquivos com os produtos
   e as novas quantidades. Formatos aceitos: `.xlsx`, `.xlsm`, `.xls`, `.csv`,
   `.txt`. Ao selecionar, abre a tela de verificação de colunas (ver abaixo).
2. **Sem cabeçalho** — marque quando os arquivos não têm linha de título; as
   colunas passam a ser tratadas por posição (`Coluna 1`, `Coluna 2`…).
3. **Verificar no banco** (opcional) — depois de confirmar as colunas, confira
   os códigos contra o banco Firebird (ver abaixo).
4. **Salvar SQL em** — escolha o caminho do `.sql` a ser gerado.
5. **Data / Hora de inserção** — data e hora do lançamento (padrão: agora).
6. **Texto histórico** — descrição do lançamento (padrão: `AJUSTE DE ESTOQUE`;
   máximo de 200 caracteres).
7. Clique em **Gerar SQL**.

As linhas ignoradas (em branco, sem produto/quantidade, ou com valor inválido)
aparecem na área de log, e as demais são gravadas normalmente.

## Unificar múltiplos arquivos

Dá para selecionar vários arquivos de uma vez (por exemplo, uma contagem por
loja ou por setor) e gerar **um único** script SQL com tudo. Regras:

- Os arquivos são concatenados **por posição**, adotando os nomes de coluna do
  primeiro arquivo — então layouts iguais com cabeçalhos ligeiramente diferentes
  ainda unificam.
- Todos precisam ter o **mesmo número de colunas**; se algum divergir, a
  importação para e aponta qual arquivo está fora do padrão.
- O mapeamento de colunas é feito **uma vez**, sobre o conjunto unificado.

## Verificação/mapeamento de colunas

Como os arquivos vêm de origens variadas, o nome e a posição das colunas mudam.
Ao carregar, a tela **Verificar colunas** mostra uma prévia (primeiras linhas) e
dois seletores:

- **Coluna do produto (PRODUTOS_ID)**
- **Coluna da nova quantidade**

Quando os nomes batem com `PRODUTOS_ID` / `PRODUTO_NOVA_QUANTIDADE`, os
seletores já vêm preenchidos; caso contrário, escolha manualmente. O botão
**Confirmar** só habilita com as duas colunas selecionadas e distintas. É
possível reabrir essa tela pelo botão **Verificar colunas…**.

## Verificação no banco (Firebird 2.5)

Antes de gerar o SQL, dá para conferir se os códigos da contagem existem no
banco. Com o mapeamento confirmado, clique em **Verificar no banco…** e informe
os dados de conexão (servidor, porta, arquivo/alias do banco, usuário, senha,
charset — padrões `localhost:3050`, `SYSDBA`, `WIN1252`).

Cada código distinto da coluna de produto é classificado em:

- **PRODUTOS** — bate com `PRODUTOS.PRODUTOS_ID` (apenas códigos inteiros);
- **PRODUTOSREFERENCIAS** — bate com `PRODUTOSREFERENCIAS.PRODUTO_REFERENCIA`
  (referência/EAN em texto), resolvendo o `PRODUTOS_ID` correspondente;
- **Ausentes** — sem correspondência em nenhuma das duas.

O relatório mostra os totais, as referências resolvidas (código → PRODUTOS_ID) e
a lista dos não encontrados. Notas:

- Um código que existe como produto tem prioridade sobre a referência.
- As consultas são parametrizadas e feitas em lotes (limite de parâmetros do
  Firebird 2.5).
- A senha é usada apenas na sessão, não é gravada em disco.
- O driver `fdb` é carregado sob demanda; sem ele (ou sem a `fbclient`), a
  verificação exibe uma mensagem clara e o resto do app continua funcionando.

## Formato do arquivo de contagem

O arquivo precisa ter, no mínimo, uma coluna de produto e uma de quantidade. A
ordem, o nome e as demais colunas não importam — o vínculo é feito na tela de
mapeamento. Quando os nomes abaixo estão presentes, o mapeamento é automático:

| Coluna                    | Descrição                          |
| ------------------------- | ---------------------------------- |
| `PRODUTOS_ID`             | ID inteiro do produto              |
| `PRODUTO_NOVA_QUANTIDADE` | Nova quantidade contada em estoque |

Detalhes do parsing:

- **CSV/TXT**: o delimitador (`;`, `,`, tab ou `|`) é detectado automaticamente.
- **Sem cabeçalho**: quando a opção está marcada, a primeira linha já é dado e as
  colunas ficam posicionais (`Coluna 1`, `Coluna 2`…).
- **Números**: aceita tanto `1234.56` quanto o formato pt-BR `1.234,56`.
- **Quantidade**: gravada com até 5 casas decimais, batendo com o domínio
  `NUMERIC(14,5)` das tabelas.
- **Campos vazios ou inválidos**: a linha é ignorada e reportada no log, sem
  interromper o processamento das demais.

## Exemplo de saída

```sql
EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'AJUSTE DE ESTOQUE', 10, '28-SET-2026 10:00:00');
EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(2, 'AJUSTE DE ESTOQUE', 5.5, '28-SET-2026 10:00:00');
```

## Desenvolvimento

Instale as dependências de desenvolvimento e rode os testes:

```bash
pip install -r requirements-dev.txt
pytest
```

Organização dos módulos:

- `kardex_app/core.py` — lógica de negócio (leitura, unificação, validação,
  geração de SQL), sem dependência de GUI e coberta por testes;
- `kardex_app/db.py` — conexão Firebird 2.5 e verificação de códigos;
- `kardex_app/gui.py` — janela principal;
- `kardex_app/mapeamento.py` — tela de mapeamento de colunas;
- `kardex_app/verificacao.py` — tela de verificação no banco;
- `kardex_app/tema.py` / `kardex_app/icones.py` — tema claro/escuro.

Os DDLs de referência das tabelas estão em `ddl/`.
