# Padrao de Nomenclatura

## Objetivo

Definir convencoes iniciais de nomes para contratos, datasets, camadas Medallion, Data Products e documentos da plataforma.

O objetivo e manter consistencia desde o onboarding das primeiras fontes: Motan, SAP e INJET.

## Principios

- nomes devem ser claros e previsiveis;
- nomes tecnicos devem evitar abreviacoes pouco conhecidas;
- contratos devem separar fonte de Data Product;
- nomes de arquivos devem ser estaveis e versionaveis;
- nomes devem refletir dominio, fonte e finalidade do dado.

## Arquivos E Pastas

Usar `kebab-case` para arquivos e pastas de documentacao e contratos.

Exemplos:

```text
motan-opc-readings-raw.yaml
motan-order-context.yaml
sap-production-orders.yaml
manufacturing-dosage-control.yaml
hybrid-data-platform.md
```

## Contratos De Fonte

Formato recomendado:

```text
contracts/sources/<source-system>/<dataset-name>.yaml
```

Exemplos:

```text
contracts/sources/motan/motan-opc-readings-raw.yaml
contracts/sources/sap/sap-production-orders.yaml
contracts/sources/injet/injet-machine-current-order.yaml
```

## Contratos De Data Product

Formato recomendado:

```text
contracts/data-products/<domain>/<data-product-name>.yaml
```

Exemplo:

```text
contracts/data-products/manufacturing/manufacturing-dosage-control.yaml
```

## Data Products

Documentacao de Data Products deve ficar em:

```text
data-products/<data-product-name>/README.md
```

Exemplo:

```text
data-products/manufacturing-dosage-control/README.md
```

## Pipelines Source-to-Landing

Configuracoes por fonte devem ficar em:

```text
pipelines/sources/<source>/datasets.yaml
pipelines/sources/<source>/sql/<dataset>.sql
```

Exportadores reutilizaveis devem ficar em:

```text
pipelines/exporters/
```

Evitar nomes de pastas baseados apenas em ondas temporarias, como `wave1`, para artefatos executaveis. O conceito de onda pode existir na configuracao, mas a estrutura principal deve ser organizada por fonte.

SQLs de extracao nao devem usar prefixos de camada Fabric no nome do arquivo.

Exemplos corretos:

```text
order_context.sql
actual_consumption_by_order.sql
sap_production_orders.sql
order_plan_vs_actual_reference.sql
```

Evitar:

```text
bronze_motan_order_context.sql
gold_manufacturing_dosage_control.sql
```

As camadas Fabric devem ser registradas como metadados em `datasets.yaml`, por exemplo `target_fabric_layer` e `target_fabric_table`.

## Datasets Analiticos

Usar `snake_case` para nomes de tabelas, views e datasets analiticos.

Exemplos:

```text
motan_order_context
motan_actual_consumption_by_order
sap_production_orders
sap_production_order_components
manufacturing_dosage_control
```

## Camadas Medallion

Quando o nome fisico exigir indicar a camada, usar prefixos simples:

```text
bronze_<source>_<dataset>
silver_<domain>_<entity>
gold_<domain>_<data_product_or_metric>
```

Exemplos:

```text
bronze_motan_order_context
bronze_sap_production_orders
silver_manufacturing_order_consumption
gold_manufacturing_dosage_control
```

## Fontes

Nomes canonicos iniciais das fontes:

```text
motan
sap
injet
```

Evitar alternar nomes como:

```text
gravimetrico
dosador
sap-b1
service-layer
```

Esses termos podem aparecer em descricoes, mas o identificador principal da fonte deve permanecer estavel.

## Dominios

Dominios canonicos:

```text
finance        (SAP Business One: notas de entrada, transferencias, servicos)
manufacturing  (dosador Motan, OPs SAP, INJET)
```

Novos dominios devem ser criados apenas quando houver owner, consumidores e escopo claros.

## Estrategia De Carga

Declarada por dataset em `load_mode` no `datasets.yaml`:

- `incremental`: a extracao entrega uma janela por coluna de atualizacao
  (watermark); Bronze e Silver fazem MERGE por `upsert_keys`;
- `full`: a extracao entrega o conjunto inteiro; o ultimo run completo substitui
  a tabela.

Datasets sem coluna de atualizacao confiavel e sem chave estavel nao sustentam
`incremental`.

## Campos

Usar `snake_case` em ingles para campos de datasets, ja a partir do SQL de
extracao, iguais aos nomes do contrato. Os nomes originais da fonte (ex.:
`OPCH.DocEntry`) ficam documentados no campo `source` do contrato.

Exemplos:

```text
order_number
machine
started_at
ended_at
planned_resin_total_kg
actual_consumed_total_kg
variance_percent
comparison_status
```

Campos vindos da origem podem ser preservados em areas raw ou payloads, mas devem ser normalizados em Silver e Gold quando fizer sentido.

## Timestamps

Preferir sufixo `_at` para timestamps de evento ou processamento.

Exemplos:

```text
started_at
ended_at
synced_at
collector_timestamp
source_timestamp
server_timestamp
```

## Unidades

Quando uma metrica possuir unidade relevante, incluir a unidade no nome do campo em Silver e Gold.

Exemplos:

```text
planned_resin_total_kg
actual_consumed_total_kg
variance_kg
duration_minutes
variance_percent
```

## Status

Campos de status devem terminar com `_status` quando representarem classificacao textual.

Exemplos:

```text
comparison_status
sap_status
sap_date_match_status
```

Campos booleanos devem preferir prefixos como `is_`, `has_` ou descricoes booleanas claras.

Exemplos:

```text
sap_released_for_production
has_open_window
```

## Convencoes Para OP

Usar `order_number` como nome padrao para ordem de producao nos datasets analiticos.

Nomes de origem como `nrOP`, `DocumentNumber` ou `svOrderNumber` devem ser documentados no campo `source` dos contratos.

## O Que Evitar

- misturar portugues e ingles em nomes tecnicos;
- usar abreviacoes sem contexto;
- criar nomes baseados apenas na ferramenta;
- usar nomes genericos como `dados`, `tabela_final` ou `resultado`;
- colocar camada, fonte e dominio de forma inconsistente.

## Revisao

Este padrao deve ser revisado quando novas fontes, dominios ou camadas fisicas forem criadas no Fabric.
