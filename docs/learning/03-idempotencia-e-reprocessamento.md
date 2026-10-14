# 03 - Idempotencia E Reprocessamento

## 1. Conceito

Uma carga e **idempotente** quando executa-la de novo, com a mesma entrada, deixa
o destino exatamente igual. E o que permite:

- dar retry sem medo;
- reprocessar um dia que deu errado;
- confiar que a contagem de linhas nao "cresce sozinha".

| Modo de escrita | O que faz | Idempotente quando |
|---|---|---|
| `overwrite` | apaga e reescreve a tabela | a entrada e o conjunto completo (snapshot) |
| `append` | so adiciona | cada lote e gravado uma unica vez (controle por run) |
| `MERGE` | atualiza se existe, insere se nao | ha chave confiavel e uma regra clara de "versao mais nova" |

Regra pratica: **toda linha sabe de onde veio** e **toda tabela sabe o que ja leu**.

## 2. Onde Aparece No Projeto

Cada run do exportador grava em uma pasta propria e escreve o manifest por ultimo:

```text
data/landing/finance/sap/purchase_invoices/ingestion_date=2026-10-14/run_id=20261014120000/part-000.parquet
data/landing/finance/sap/_manifests/ingestion_date=2026-10-14/run_id=20261014120000/manifest.json
```

A carga do Bronze esta em `local/medallion.py` (polars + Delta) e em
`fabric/finance/nb_bronze_sap.Notebook` (Spark), com as mesmas regras.

## 3. A Versao Ingenua E Por Que Falha

Esta e a primeira forma que quase todo mundo escreve:

```python
df = spark.read.parquet("Files/sap/purchase_invoices/*/*/*.parquet")   # TODOS os runs
df = df.withColumn("_bronze_loaded_at", F.current_timestamp())         # mesmo valor em todas as linhas
df.write.format("delta").mode("overwrite").saveAsTable("bronze_sap_purchase_invoices")

latest = Window.partitionBy("doc_entry").orderBy(F.desc("_bronze_loaded_at"))  # desempate arbitrario
```

- **Rele tudo a cada execucao.** Rodando de hora em hora, sao ~720 runs por mes;
  o custo cresce sem parar e um arquivo ruim de meses atras quebra a carga.
- **"Mais recente" que nao e.** `current_timestamp()` e avaliado uma vez por
  execucao, entao o `row_number()` escolhe uma versao qualquer.
- **Le run pela metade.** Sem olhar o manifest, um run que falhou no meio entra.
- **Ordena por `run_id`.** Se uma pipeline usa o numero do build (`420`) e uma
  execucao local usa timestamp (`20261014120000`), o run local sempre "vence"
  ([ADR 0004](../adr/0004-run-ordering-by-manifest.md)).

## 4. A Versao Correta

Trechos de `local/medallion.py`:

```python
runs = completed_runs(landing, domain, source)        # so runs com manifest, ordenados por started_at
done = lake.loaded_runs("bronze", name)               # tabela de controle ctrl_ingested_runs
new_runs = [r for r in candidates if r.run_id not in done]
if not new_runs:
    return f"{table}: nada novo"                      # segunda execucao: nao grava nada
```

```python
DeltaTable(path).merge(incoming, predicate="t.doc_entry = s.doc_entry", source_alias="s", target_alias="t") \
    .when_matched_update_all(predicate="s._run_started_at > t._run_started_at") \  # nunca volta no tempo
    .when_not_matched_insert_all() \
    .execute()
lake.record_runs("bronze", name, new_runs, counts)   # so registra quando algo entrou
```

- `_run_started_at` vem do manifest: e um horario real, comparavel entre
  orquestradores.
- A condicao do MERGE garante que reprocessar um run antigo nao sobrescreve dado
  mais novo.
- Datasets `full` usam so o ultimo run completo e `overwrite`: tambem idempotente.

## 5. Exercicio

1. Rode `python run_demo.py` e compare as etapas 6 e 7. Por que a etapa 7 mostra
   "nada novo" em todo o Bronze?
2. Rode `pytest tests/test_end_to_end.py -k idempotent` e leia o teste: o que ele
   compara para provar que nada mudou?
3. Apague a pasta `data/lakehouse/ctrl_ingested_runs` e rode
   `python local/medallion.py`. O Bronze reprocessa todos os runs, mas as
   contagens do Silver continuam iguais. Qual parte do MERGE garante isso?
4. Apague o manifest do ultimo run de `finance/sap/_manifests/` (mantendo os
   Parquet) e recrie o lakehouse do zero. O que aconteceu com as alteracoes
   desse run? Por que esse e o comportamento desejado para um run incompleto?
