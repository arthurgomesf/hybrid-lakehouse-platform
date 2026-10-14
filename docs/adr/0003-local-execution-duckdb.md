# ADR 0003: Execucao Local Com DuckDB E Delta Lake Sem Spark

## Status

Aceita

## Contexto

O ambiente analitico na nuvem (lakehouse com Spark) era um trial com prazo de
expiracao, e as fontes reais (SAP HANA, Postgres do chao de fabrica) so existem
na rede interna. Isso impedia testar o pipeline inteiro, mostrar o projeto e
rodar CI.

## Decisao

- Fontes ficticias em DuckDB (`scripts/generate_fake_data.py`), com as mesmas
  tabelas e colunas do SAP B1 e as mesmas views do `data-collector`.
- Compatibilidade de SQL por macros (`ADD_DAYS`, `DAYS_BETWEEN`) e uma tabela
  `DUMMY`, para que o SQL de producao rode sem alteracao.
- O exportador ganha `engine: duckdb`; nada mais muda.
- Bronze/Silver/Gold locais em polars + `deltalake` (`local/medallion.py`), com as
  mesmas regras dos notebooks Spark em `fabric/`.
- Casos de borda plantados no gerador e cobertos por testes de ponta a ponta.

## Consequencias

- `python run_demo.py` mostra backfill, incremental, MERGE e idempotencia em
  segundos, sem credencial nenhuma;
- o CI roda o fluxo completo a cada push;
- as regras existem em dois motores (polars e Spark): mudancas precisam ser
  feitas nos dois, e os testes so cobrem a versao local.
