# Trilha De Aprendizado

Conceitos de engenharia de dados explicados com o codigo deste repositorio.
Cada modulo segue o formato:

1. conceito em linguagem simples;
2. onde aparece no projeto (arquivo real);
3. a versao ingenua e por que ela falha;
4. a versao correta (codigo daqui);
5. exercicio que voce roda localmente com `python run_demo.py`.

## Modulos

| # | Modulo | Codigo de referencia |
|---|---|---|
| 03 | [Idempotencia e reprocessamento](03-idempotencia-e-reprocessamento.md) | `local/medallion.py`, `fabric/*/nb_bronze_*` |

Proximos modulos planejados: arquitetura medallion, extracao full x incremental
e watermark, data contracts e schema drift, CI/CD, qualidade e observabilidade,
seguranca e segredos, modelagem dimensional e consumo.

## Glossario

| Termo | Significado |
|---|---|
| Landing | Area de chegada dos arquivos brutos (`landing/` no ADLS, `data/landing` local). |
| Bronze | Primeira tabela Delta; dado como veio, mais colunas de linhagem. |
| Silver | Versao mais recente por chave, com as regras criticas do contrato aplicadas. |
| Gold | Dado modelado para uma pergunta de negocio (Data Product). |
| Run | Uma execucao do exportador, com `run_id` e manifest proprios. |
| Manifest | Arquivo gravado por ultimo em cada run; marca o run como completo. |
| Watermark | Coluna usada para buscar so o que mudou (ex.: `UpdateDate`). |
| Idempotencia | Executar de novo com a mesma entrada nao muda o resultado. |
| MERGE | Atualiza se a chave existe, insere se nao existe. |
| Grao | O que uma linha representa (ex.: uma linha por nota fiscal). |
| Schema drift | Mudanca de nomes ou tipos de colunas entre execucoes. |
| Linhagem | Rastro de onde cada linha veio (arquivo, run, horario). |
| Data Contract | Acordo escrito sobre schema, grao, chave, qualidade e dono de um dataset. |
| Shortcut | Atalho do lakehouse que expoe o ADLS sem copiar os dados. |
