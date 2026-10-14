# Datasets Candidatos ao Fabric

## Objetivo

Listar os primeiros datasets candidatos a ingestao no Microsoft Fabric, respeitando a arquitetura hibrida da plataforma.

Esta lista orienta as configuracoes em `pipelines/sources/<source>/datasets.yaml` e serve como backlog tecnico para discutir prioridade, frequencia, camada alvo e custo de capacity.

## Principios

- priorizar dados com valor analitico claro;
- evitar replicacao integral de raw industrial de alta frequencia;
- usar ingestao incremental sempre que possivel;
- publicar dados em Parquet na landing cloud antes da carga no Fabric;
- manter o TimescaleDB como fonte operacional para detalhes de baixa granularidade;
- promover para o Fabric apenas datasets governados por contrato ou candidatos a contrato.

## Lista Inicial

| Landing Dataset | Fonte | Destino Fabric Esperado | Publicacao | Frequencia Inicial | Contrato Relacionado | Justificativa |
| --- | --- | --- | --- | --- | --- | --- |
| order_context | TimescaleDB `vw_order_number_changes` | `bronze_motan_order_context` | Parquet landing | 15 minutos | `motan-order-context` | Define a janela temporal da OP no gravimetrico e permite correlacao com SAP e INJET. |
| actual_consumption_by_order | TimescaleDB `vw_order_actual_consumption_total` | `bronze_motan_actual_consumption_by_order` | Parquet landing | 15 minutos | `motan-actual-consumption-by-order` | Resume o consumo real por OP sem levar todo raw OPC UA para o Fabric. |
| component_consumption_by_order | TimescaleDB `vw_order_component_consumption_consolidated` | Silver futura | Parquet landing | 15 minutos | Futuro contrato `motan-component-consumption` | Permite analise de consumo por componente e comparacao detalhada com planejamento. |
| sap_production_orders | TimescaleDB `sap_production_orders` ou SAP Service Layer | `bronze_sap_production_orders` | Parquet landing | 30 minutos | `sap-production-orders` | Traz o planejamento da OP, produto, status e consumo planejado total. |
| sap_production_order_components | TimescaleDB `sap_production_order_components` ou SAP Service Layer | `bronze_sap_production_order_components` | Parquet landing | 30 minutos | `sap-production-orders` | Detalha os componentes planejados e a regra de resina/material. |
| injet_machine_current_order | INJET SQL Server ou eventos `op_sync_events` | Bronze/Silver | Parquet landing | 15 minutos | `injet-machine-current-order` | Ajuda a auditar a OP corrente da maquina e divergencias entre INJET e Motan. |
| op_sync_events | TimescaleDB `op_sync_events` | Bronze | Parquet landing | 15 minutos | `injet-machine-current-order` | Fornece rastreabilidade da sincronizacao entre INJET e Motan. |
| sap_sync_events | TimescaleDB `sap_sync_events` | Bronze | Parquet landing | 30 minutos | `sap-production-orders` | Fornece rastreabilidade da sincronizacao com SAP. |
| collector_status_events | TimescaleDB `collector_status_events` | Bronze/Silver | Parquet landing | 15 minutos | Futuro contrato `motan-collector-status` | Permite monitorar disponibilidade e confiabilidade da coleta OPC UA. |
| order_plan_vs_actual_reference | `vw_order_plan_vs_actual_consolidated` como referencia atual | `bronze_motan_order_plan_vs_actual_reference` | Parquet landing | 30 minutos | `manufacturing-dosage-control` | Referencia atual para validar o Data Product que sera materializado como Gold dentro do Fabric. |

## Fora Do Escopo Inicial

Os seguintes dados nao devem ser replicados integralmente para o Fabric nesta fase:

- `public.opc_readings` completo;
- leituras OPC UA tag a tag em alta frequencia sem agregacao;
- payloads brutos SAP completos sem uso analitico definido;
- logs tecnicos detalhados que servem apenas para troubleshooting local.

## Observacoes Por Fonte

### Motan

O raw detalhado permanece no TimescaleDB por padrao. O Fabric deve receber visoes derivadas por OP, componente, status e qualidade.

### SAP

O SAP fornece o planejamento. A ingestao pode partir do cache atual no TimescaleDB ou diretamente da Service Layer em desenho futuro.

### INJET

O INJET fornece contexto de OP corrente da maquina. A plataforma deve decidir se vai ingerir diretamente do SQL Server ou usar os eventos ja persistidos pelo `op_sync` como trilha operacional.

## Criterios De Priorizacao

Priorizar datasets que:

- sustentam o Data Product `manufacturing-dosage-control`;
- evitam alto custo de capacity;
- possuem chave de correlacao por OP;
- permitem atualizacao incremental;
- ja possuem contrato inicial;
- ajudam a monitorar qualidade e confiabilidade da integracao.

## Primeira Onda Recomendada

Para a primeira implementacao no Fabric, priorizar:

1. `order_context`;
2. `actual_consumption_by_order`;
3. `sap_production_orders`;
4. `sap_production_order_components`;
5. `order_plan_vs_actual_reference`.

Essa onda entrega valor analitico com baixo volume relativo e evita copiar o raw OPC UA completo.

## Pendencias

- validar frequencias de ingestao com manufatura;
- definir SLAs iniciais;
- definir se o Fabric consumira SAP pelo cache atual ou diretamente pela Service Layer;
- definir se o Fabric consumira INJET diretamente ou via eventos do `op_sync`;
- criar contrato futuro para consumo por componente;
- criar contrato futuro para status do coletor Motan.
- criar pipeline Azure DevOps para executar `pipelines/exporters/source_to_landing.py`.
