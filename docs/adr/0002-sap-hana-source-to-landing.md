# ADR 0002: Ingestao SAP HANA Via Source-to-Landing

## Status

Aceita (revisada na versao 0.2 dos contratos)

## Contexto

O SAP Business One (HANA) e a fonte corporativa do dominio `finance`. O acesso e
por ODBC a partir da rede interna; a plataforma analitica na nuvem nao acessa o
banco diretamente.

## Decisao

- Um agente self-hosted do Azure DevOps roda `source_to_landing.py` perto do SAP.
- Cada execucao gera Parquet + `manifest.json` na landing (ADLS).
- `purchase_invoices` e incremental por **`UpdateDate`** com janela movel
  (`window_days`), chave `doc_entry`. A primeira versao usava `DocDate` e perdia
  alteracoes e cancelamentos de documentos antigos.
- Documentos cancelados sao extraidos com `is_cancelled`, em vez de filtrados,
  para que o cancelamento chegue ao Silver.
- Datasets sem coluna de atualizacao confiavel sao `full` desde `start_date`.
- Nomes de colunas saem do SQL ja em snake_case em ingles, iguais ao contrato.
- Credenciais ficam em secret variables / Key Vault, nunca no repositorio.

## Consequencias Positivas

- fonte e lakehouse desacoplados; landing permite auditoria e reprocessamento;
- o mesmo exportador serve para novas tabelas SAP e outras fontes;
- o mesmo SQL roda no HANA e localmente (DuckDB com macros `ADD_DAYS`/`DAYS_BETWEEN`).

## Trade-offs

- alteracoes anteriores a janela exigem um backfill (`--window-days` maior);
- exclusao fisica nao e detectada (o SAP B1 cancela em vez de excluir);
- o agente precisa estar sempre ligado; um agente em estacao de trabalho gera
  filas de execucoes canceladas quando a maquina desliga.
