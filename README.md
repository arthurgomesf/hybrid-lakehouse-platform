# Hybrid Data Platform - On-Prem ERP & Shop Floor to Lakehouse

> **EN** - A hybrid data platform that moves data from an on-premise ERP (SAP
> Business One on HANA) and a shop-floor data collector into a medallion
> lakehouse (Microsoft Fabric), driven by data contracts. Everything runs
> locally with fictitious data: `python run_demo.py`.

Plataforma de dados hibrida: extrai dados de um ERP on-premise (SAP Business One
em HANA) e do coletor de chao de fabrica, publica em uma landing no ADLS e
transforma em Bronze, Silver e Gold no lakehouse - com **data contracts**
guiando schema, chaves e qualidade.

Este repositorio e a versao publica de um projeto real: empresas, fornecedores,
maquinas e numeros sao **ficticios** (Contoso e Fabrikam), e as regras de negocio
foram generalizadas. O fluxo inteiro roda no seu computador, sem nenhuma conexao.

## Arquitetura

```text
 ON-PREMISE                        NUVEM                                         CONSUMO
 SAP B1 (HANA) ---+
                  | agente     ADLS landing (Parquet     Lakehouse (Delta)
 data-collector --+-----------> + manifest por run) ----> Bronze -> Silver -> Gold ---> Power BI
 (Postgres)         exportador                                                          (Direct Lake)
                    Python      contrato = schema        ctrl_ingested_runs + MERGE
```

| Camada | O que garante |
|---|---|
| Exportador | schema do contrato (coluna vazia nao perde o tipo), falha em schema drift, retry so em erro transitorio, manifest por ultimo |
| Landing | arquivos imutaveis por run; mesmo layout local e na nuvem |
| Bronze | so le runs completos (com manifest), linhagem por linha, idempotente |
| Silver | versao mais recente por chave, chave unica e nao nula ou nao publica |
| Gold | calculado no lakehouse, com teste de paridade contra a view on-prem que substitui |

Detalhes: [arquitetura](docs/architecture/hybrid-data-platform.md),
[ingestao](docs/architecture/source-to-landing-ingestion.md), [ADRs](docs/adr/).

## Rodando Em 3 Comandos

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_demo.py
```

A demo:

1. gera as fontes ficticias em DuckDB (tabelas do SAP B1 de duas empresas + views
   do coletor), com casos de borda plantados;
2. exporta tudo para `data/landing` (backfill);
3. carrega Bronze, Silver e Gold em Delta (`data/lakehouse`);
4. altera as fontes (edicoes, cancelamento, documentos novos, primeiro CSRF);
5. exporta de novo com a janela incremental de 7 dias;
6. carrega de novo: so as mudancas entram, via MERGE;
7. roda uma terceira vez: nada muda (idempotencia).

Para ver o resultado (tabelas por camada, runs carregados e uma amostra da Gold):

```bash
python scripts/inspect_lakehouse.py
python scripts/inspect_lakehouse.py --table silver_finance_purchase_invoices --rows 5
```

```bash
pytest -q                                # unidade + ponta a ponta
python scripts/check_sensitive.py        # nenhum identificador real no repositorio
```

## O Que Tem Aqui

| Pasta | Conteudo |
|---|---|
| `pipelines/exporters/` | exportador generico (HANA, Postgres, DuckDB) |
| `pipelines/sources/<fonte>/` | `datasets.yaml` + SQL de extracao (o mesmo SQL roda no HANA e no DuckDB) |
| `pipelines/azure-devops/` | agendamento em agentes self-hosted |
| `contracts/` | data contracts de fonte e de Data Product |
| `local/medallion.py` | Bronze/Silver/Gold com polars + Delta Lake, sem Spark |
| `fabric/` | notebooks Spark, pipelines e semantic model (formato Git Integration) |
| `scripts/` | gerador de dados ficticios, inspetor do lakehouse local e verificador de dados sensiveis |
| `tests/` | testes de unidade e de ponta a ponta |
| `docs/` | arquitetura, ADRs, padroes, [licoes aprendidas](docs/lessons-learned.md) e [trilha de aprendizado](docs/learning/00-index.md) |

## Decisoes Que Valem A Leitura

- [Licoes aprendidas](docs/lessons-learned.md): os problemas reais da primeira
  versao (tipos inferidos, watermark errado, ordem de runs, agente em estacao de
  trabalho...) e como cada um foi resolvido.
- [ADR 0004](docs/adr/0004-run-ordering-by-manifest.md): por que a ordem entre
  runs vem do manifest e nunca do `run_id`.
- [ADR 0003](docs/adr/0003-local-execution-duckdb.md): como o mesmo SQL de
  producao roda localmente.

## Stack

Python, SQL (SAP HANA / DuckDB / Postgres), polars, Delta Lake, PySpark,
Microsoft Fabric (lakehouse, pipelines, Direct Lake), Azure Data Lake Storage,
Azure DevOps (agentes self-hosted), GitHub Actions.

## Licenca

[MIT](LICENSE).
