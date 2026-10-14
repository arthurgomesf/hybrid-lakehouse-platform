# Padrao de Data Contracts

## Objetivo

Definir um formato minimo para Data Contracts da plataforma corporativa de dados.

O objetivo nao e criar documentacao extensa, mas garantir que fontes e Data Products sejam descritos de forma consistente, governavel e evolutiva.

## Tipos de Contrato

### Source Contract

Usado para documentar uma fonte de dados ou uma interface proxima da origem.

Exemplos:

- Motan OPC UA;
- SAP Service Layer;
- INJET SQL Server;
- tabelas ou views operacionais on-premise.

Um Source Contract nao significa que o dataset sera copiado integralmente para o Fabric.

### Data Product Contract

Usado para documentar um produto de dados analitico, normalmente consumido por areas de negocio, Power BI, APIs ou outros produtos.

Exemplos:

- controle de dosagem real vs planejado;
- indicadores de qualidade;
- acompanhamento de producao.

## Localizacao

Contratos de fonte devem ficar em:

```text
contracts/sources/<source-system>/<contract-name>.yaml
```

Contratos de Data Products devem ficar em:

```text
contracts/data-products/<domain>/<contract-name>.yaml
```

## Estrutura Minima Para Source Contracts

```yaml
contract:
  name:
  type: source
  domain:
  owner:
  technical_owner:
  source_system:
  description:
  status:
  version:

dataset:
  name:
  layer:
  storage_location:
  fabric_replication:
  refresh_frequency:
  grain:
  primary_keys:

source:
  application:
  database:

schema:
  fields:
    - name:
      type:
      nullable:
      description:
      source:

quality_rules:
  - name:
    description:
    severity:

known_limitations:
  - item

open_questions:
  - question
```

## Estrutura Minima Para Data Product Contracts

```yaml
contract:
  name:
  type: data-product
  domain:
  owner:
  technical_owner:
  description:
  status:
  version:

data_product:
  name:
  business_capability:
  target_layer:
  target_platform:
  fabric_replication:
  grain:
  primary_keys:

inputs:
  - contract:
    role:
    source_system:
    required_fields:

output_schema:
  fields:
    - name:
      type:
      nullable:
      description:
      source:

business_rules:
  rule_name:
    description:

quality_rules:
  - name:
    description:
    severity:

known_limitations:
  - item

open_questions:
  - question
```

## Tipos De Campo

Os tipos do contrato definem o schema do Parquet gravado pelo exportador:

| Tipo no contrato | Tipo no arquivo |
|---|---|
| `string`, `jsonb` | texto (json serializado) |
| `integer` | inteiro 64 bits |
| `decimal` | decimal(38, 6) - valores monetarios |
| `numeric` | ponto flutuante - medidas fisicas |
| `boolean` | booleano |
| `date` | data |
| `timestamp` / `timestamptz` | timestamp sem fuso / em UTC |

Uma coluna devolvida pela query que nao esteja no contrato (ou o contrario)
interrompe a exportacao.

## Campos Obrigatorios

Todo contrato deve conter:

- `contract.name`;
- `contract.type`;
- `contract.domain`;
- `contract.owner`;
- `contract.technical_owner`;
- `contract.status`;
- `contract.version`;
- descricao do grao do dataset;
- schema dos campos principais;
- regras minimas de qualidade;
- limitacoes conhecidas;
- perguntas em aberto quando houver incerteza.

## Status Permitidos

- `draft`: contrato inicial, ainda em validacao;
- `active`: contrato validado e em uso;
- `deprecated`: contrato sera descontinuado;
- `retired`: contrato nao e mais utilizado.

## Severidade Das Regras De Qualidade

- `critical`: quebra confiabilidade basica do dataset;
- `warning`: indica risco ou anomalia que deve ser monitorada;
- `info`: regra informativa ou recomendacao de acompanhamento.

## Convencoes

- nomes de contratos devem usar kebab-case;
- nomes de datasets fisicos ou analiticos devem usar snake_case quando representarem tabelas ou views;
- campos devem ter descricao objetiva;
- nao inventar semantica quando ela nao estiver confirmada;
- usar `SEMANTICA NAO IDENTIFICADA` quando o significado tecnico ou de negocio nao estiver claro;
- marcar contratos iniciais como `draft`;
- versionar contratos inicialmente como `0.1.0`.

## Fabric E Replicacao

O campo `fabric_replication` deve deixar claro se o dataset sera ou nao candidato ao Fabric.

Valores recomendados:

- `not_full_raw_by_default`: raw completo nao deve ser replicado integralmente por padrao;
- `candidate_for_bronze_or_silver_lightweight`: candidato a ingestao seletiva no Fabric;
- `curated_outputs_only`: apenas outputs curados devem ser publicados;
- `to_be_defined`: decisao ainda pendente.

## Boas Praticas

- contratos devem ser pequenos o suficiente para serem revisados;
- contratos devem refletir a realidade atual, nao a arquitetura desejada sem evidencias;
- regras de negocio devem ser separadas de detalhes fisicos;
- contratos de fonte e contratos de Data Product nao devem ser misturados;
- qualquer campo critico para join, tempo ou metrica deve ter regra de qualidade associada.

## Revisao Humana

Antes de marcar um contrato como `active`, validar com os responsaveis:

- significado dos campos;
- owner;
- SLA;
- frequencia;
- regras de qualidade;
- tolerancias;
- unidade oficial;
- criticidade;
- consumidores esperados.
