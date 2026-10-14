# Arquitetura Da Plataforma Hibrida

## Objetivo

Levar dados de sistemas on-premise (ERP e chao de fabrica) para um lakehouse
analitico, sem que a plataforma em nuvem acesse diretamente os bancos internos,
com rastreabilidade de cada linha ate o arquivo e a execucao que a trouxe.

## Visao Geral

```text
 ON-PREMISE                          NUVEM                                     CONSUMO
 ----------                          -----                                     -------
 SAP B1 (HANA)  --+                                                            Power BI
                  |  agente self-hosted   ADLS landing        Lakehouse        (Direct Lake)
 data-collector --+--> exportador -----> Parquet + manifest --> Bronze --> Silver --> Gold
 (Postgres)          (Azure DevOps)      por run               (Delta)
```

| Etapa | Onde roda | Responsabilidade |
|---|---|---|
| Extracao | agente self-hosted perto da fonte | SQL versionado, schema do contrato, Parquet + manifest |
| Landing | ADLS Gen2 (`landing/<dominio>/<fonte>/...`) | arquivos imutaveis por run; desacopla fonte e lakehouse |
| Bronze | lakehouse (Delta) | dado como veio + linhagem; carga idempotente |
| Silver | lakehouse (Delta) | versao mais recente por chave + regras criticas do contrato |
| Gold | lakehouse (Delta) | Data Product para uma pergunta de negocio |
| Consumo | semantic model Direct Lake | medidas com regra de negocio explicita |

Localmente, o mesmo fluxo roda com DuckDB no lugar das fontes e Delta Lake via
`deltalake` no lugar do Spark (ver [ADR 0003](../adr/0003-local-execution-duckdb.md)).

## Fontes

### SAP Business One (dominio `finance`)

- Duas empresas em bancos separados (`SBO_CONTOSO_PRD`, `SBO_FABRIKAM_PRD`).
- Acesso por ODBC a partir da rede interna; o lakehouse nunca conecta no HANA.
- Datasets: `purchase_invoices` (incremental por `UpdateDate`),
  `return_transfers` e `service_invoices` (snapshot desde `start_date`).

### Dosador Motan e cache SAP de OPs (dominio `manufacturing`)

- Leituras OPC UA de alta frequencia ficam no TimescaleDB on-premise
  ([ADR 0001](../adr/0001-hybrid-analytical-platform.md)); so visoes por OP vao
  para a nuvem.
- Ordens de producao do SAP chegam por um cache do `data-collector` (via Service
  Layer), nao pelo HANA.
- Datasets: janelas de OP, consumo real por janela, OPs e componentes SAP e a
  view consolidada on-premise usada como referencia de paridade.

## Contratos Entre As Camadas

| Contrato | Garantido por |
|---|---|
| Schema do arquivo = schema do contrato | exportador (`build_frame`), falha em coluna extra/faltante |
| Run so e lido quando completo | manifest gravado por ultimo; Bronze le a partir dos manifests |
| Ordem entre runs | `_run_started_at` do manifest ([ADR 0004](../adr/0004-run-ordering-by-manifest.md)) |
| Reprocessar nao duplica | tabela `ctrl_ingested_runs` + MERGE condicional |
| Silver confiavel | chave unica e nao nula, senao a publicacao e bloqueada |

## Layout Da Landing

```text
landing/<dominio>/<fonte>/<dataset>/ingestion_date=YYYY-MM-DD/run_id=<id>/part-000.parquet
landing/<dominio>/<fonte>/_manifests/ingestion_date=YYYY-MM-DD/run_id=<id>/manifest.json
```

`ingestion_date` e definido uma vez por execucao do orquestrador, para que um
retry regrave o mesmo caminho em vez de criar outro.

## Criterios Para Levar Um Dataset Ao Lakehouse

- apoia decisao de negocio e tem dono;
- tem contrato com grao e chave;
- pode ser atualizado de forma incremental ou e pequeno o bastante para snapshot;
- nao e raw de alta frequencia sem agregacao.
