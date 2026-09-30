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
- **Códigos repetidos são somados**: o mesmo produto aparecendo em arquivos (ou
  linhas) diferentes vira um único lançamento com a soma das quantidades. Como o
  código é tratado como inteiro, zeros à esquerda não separam (`007` e `7` somam
  no produto `7`).

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

### Zerar itens não contados

Marque **Zerar estoque dos itens não contados** antes de gerar o SQL. Ao salvar,
o app consulta o banco, lista os **produtos ativos** (`PRODUTO_INATIVO = 0`) que
**não** apareceram na contagem e embute, **no mesmo `.sql`**, um `EXECUTE
PROCEDURE KARDEX_ALTERA_QUANTIDADE(..., 0, ...)` para cada um. Útil para
reconciliação total: o que não foi contado é tratado como estoque zero.

A conexão informada na tela **Verificar no banco…** é reaproveitada — se você já
verificou os códigos, o banco não é pedido de novo. Os lançamentos de zeramento
entram depois da contagem.

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
EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(1, 'AJUSTE DE ESTOQUE', 10, '2026-09-28 10:00:00');
EXECUTE PROCEDURE KARDEX_ALTERA_QUANTIDADE(2, 'AJUSTE DE ESTOQUE', 5.5, '2026-09-28 10:00:00');
```

A data usa o formato ISO (`YYYY-MM-DD HH:MM:SS`), interpretado pelo Firebird
independentemente do idioma da conexão. Os lançamentos saem ordenados por
código. Não há bloco de recompute separado: a própria `KARDEX_ALTERA_QUANTIDADE`
recomputa o estoque do produto ao final.

## Modo lote (inserts em lote)

Além do modo padrão (chamando `KARDEX_ALTERA_QUANTIDADE` por item), há o
checkbox **Modo lote**. Ele faz a **mesma coisa que a procedure**, mas via
INSERT bruto no `KARDEX`, o que é mais rápido em bases grandes:

- para cada produto, calcula o **delta** = contagem − estoque na data e insere
  **um** movimento (entrada se positivo, saída se negativo), na data informada;
- delta 0 é pulado; com **zerar não contados** marcado, os ativos ausentes da
  contagem entram com alvo 0 (delta = −estoque);
- em seguida chama `KARDEX_RECOMPUTA` para o produto.

Replica a lógica da procedure (preço = `PRODUTO_PRECO_CUSTO`, entrada/saída,
origem 5). Roda **sequencial** (a ordem insert→recompute importa) e sempre com
**backup** antes. Como a `KARDEX_RECOMPUTA` recalcula o saldo e **proíbe estoque
negativo**, um produto pode ser recusado se o ajuste o levar a negativo — o
mesmo que aconteceria pela procedure. Por fazer INSERT direto, valide num
backup/base de teste antes de usar em produção.

## Conferir resultado

Depois de aplicar o ajuste, o botão **Conferir resultado…** compara a contagem
com o **estoque na data/hora selecionada** (o `KARDEX_NOVO_ESTOQUE` até aquela
data, incluindo o lançamento do ajuste) — **não** o estoque atual, para que
movimentos posteriores à contagem não gerem falso conflito. Lista, numa tabela,
o que ficou **OK** ou **divergente** (contado × estoque na data × diferença).
Produto sem movimento até a data conta como estoque 0.

A consulta é **paralela** (usa o campo *Conexões paralelas*), com barra de
progresso e opção de cancelar — bem mais rápida em bases grandes, já que é
somente leitura.

## Executar no banco (direto do app)

Depois de confirmar as colunas, o botão **Executar no banco…** roda os
lançamentos direto no Firebird (via `fdb`), numa thread, sem precisar do
`.bat`/`.ps1`. Mostra:

- **barra de progresso** com porcentagem e `feito/total`;
- **tempo decorrido**, **velocidade** (lançamentos/s) e **ETA**;
- **estatísticas de transação/servidor** ao vivo — OIT/OAT/OST/próxima
  transação, transações ativas e I/O de páginas — atualizadas a cada COMMIT.

Comita a cada X registros (mesmo campo), tem **Cancelar** (faz rollback do que
ainda não foi commitado) e pede confirmação antes de alterar o estoque. Pula
códigos fora de `PRODUTOS` e aplica o zeramento se marcado.

A execução é **paralela**: o campo **Conexões paralelas** (padrão 4) define
quantas conexões/transações simultâneas processam os lançamentos. Como cada
produto é independente no `KARDEX`, os lançamentos são divididos entre as
conexões sem conflito (a ordem por código é dispensada), acelerando bastante em
bases grandes. Cada conexão comita a cada X e, em cancelamento, desfaz apenas o
seu próprio lote não commitado.

**Falhas são por produto, não travam tudo:** cada produto roda isolado por
`SAVEPOINT`. Se a `KARDEX_RECOMPUTA` recusar um item (ex.: o ajuste levaria a
estoque negativo por causa de movimentos posteriores à contagem), o app desfaz
**só aquele produto** e segue com os demais. No fim, mostra "N aplicado(s), M
pulado(s)" e lista no log cada produto pulado com o motivo.

A **preparação** (consultas ao banco para montar os lançamentos) roda numa
thread, com uma janela *Preparando lançamentos…* — a interface não trava
enquanto isso, mesmo em bases grandes.

Com **Fazer backup do banco (gbak) antes de executar** marcado (padrão), o app
gera um `.fbk` com `gbak -b -g` antes dos lançamentos; se o backup falhar, a
execução é **abortada** e nada é alterado. Requer o `gbak.exe` do Firebird
instalado na máquina.

## Pacote executável (isql)

Marque **Gerar pacote .bat/.ps1 para rodar direto no isql** para, além do `.sql`,
criar uma pasta `<nome>_pacote/` ao lado dele com:

- `script.sql` — o SQL gerado (na codificação do charset da conexão);
- `executar.bat` e `executar.ps1` — autodetectam o `isql.exe` (Firebird
  2.5/3.0/4.0/5.0), rodam o script com `-b` (para no primeiro erro), registram
  tudo em `execucao.log` e pausam ao final.

Basta dar duplo-clique no `.bat` — bem mais rápido que colar o script no
IBExpert. A conexão informada em **Verificar no banco…** é reaproveitada.

O `.bat`/`.ps1` mostra um **contador de progresso** (`[N/Total]`), pois o
trabalho é dividido em partes (`parte_NNNN.sql`) executadas uma a uma. Códigos
que **não existem em PRODUTOS são pulados** no pacote (evita erros no isql).

O campo **COMMIT a cada X registros** controla de quantos em quantos lançamentos
o script comita — em bases grandes, blocos menores evitam uma transação única
gigante (cada `KARDEX_ALTERA_QUANTIDADE` é uma procedure individual). No pacote,
esse X também é o tamanho de cada parte.

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
