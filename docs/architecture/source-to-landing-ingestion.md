# Ingestao Source-to-Landing

## Decisao

```text
Orquestrador (Azure DevOps hoje; Airflow ou shell amanha)
  -> agente self-hosted na rede da fonte
  -> pipelines/exporters/source_to_landing.py
  -> Parquet + manifest.json por run
  -> landing (ADLS)
```

O orquestrador so agenda e passa parametros; toda a logica fica no exportador,
que e portavel.

## Configuracao Por Fonte

`pipelines/sources/<fonte>/datasets.yaml`:

| Campo | Uso |
|---|---|
| `source.name`, `source.domain`, `source.engine` | caminho na landing e engine (`hana`, `postgresql`, `duckdb`) |
| `defaults.window_days`, `defaults.start_date` | parametros `:window_days` e `:start_date` do SQL |
| `datasets[].source_sql` | SQL da extracao (sem prefixo de camada no nome) |
| `datasets[].contract` / `contract_schema` | contrato e secao com os campos (default `schema`) |
| `datasets[].load_mode` | `incremental` (MERGE) ou `full` (snapshot) |
| `datasets[].upsert_keys` | chave do MERGE e da regra de unicidade |
| `datasets[].bronze_table` / `silver_table` | tabelas de destino |

## O Que O Exportador Garante

1. **Schema do contrato**: cada coluna e convertida para o tipo do contrato; uma
   coluna vazia em todo o run continua `decimal`, e nao `null`.
2. **Drift falha cedo**: coluna a mais ou a menos que o contrato interrompe o run
   (`SchemaDriftError`) antes de qualquer arquivo ser publicado como completo.
3. **Retry so para erro transitorio**: falhas de conexao tem backoff
   exponencial; erro de SQL falha na hora.
4. **Manifest por ultimo**: e o marcador de "run completo" lido pelo Bronze.
5. **Mesmo layout local e remoto**: `--output-dir` espelha a landing.

## Execucao

```bash
# local, com as fontes ficticias
python pipelines/exporters/source_to_landing.py \
  --config pipelines/sources/sap/datasets.yaml \
  --engine duckdb --duckdb-path data/sources.duckdb --output-dir data/landing

# agente (producao): engine do yaml + upload
python pipelines/exporters/source_to_landing.py \
  --config pipelines/sources/sap/datasets.yaml \
  --run-id "$BUILD_ID" --ingestion-date "$INGESTION_DATE" --upload
```

Variaveis de ambiente esperadas no agente (sempre como secret variables / Key Vault):
`HANA_CONNECTION_STRING` ou `DATABASE_URL`, `AZURE_STORAGE_LANDING_URL`,
`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.

## Fora Do Escopo

- streaming e CDC por log;
- replicacao integral de leituras OPC UA;
- leitura em lotes (`fetchmany`) para tabelas muito grandes, ainda nao necessaria.
