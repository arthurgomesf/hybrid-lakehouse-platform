# Manufacturing Dosage Control

## Finalidade

Data Product da manufatura para comparar o consumo real dosado no gravimetrico Motan com o consumo planejado no SAP por ordem de producao.

## Fontes

- Motan Gravimetrico: leituras OPC UA, acumuladores de consumo e OP ativa no equipamento.
- SAP: ordens de producao, produto, status e componentes planejados.
- INJET: OP corrente da maquina e rastreabilidade da sincronizacao com o Motan.

## Outputs Esperados

- comparacao entre planejado SAP e realizado Motan por OP;
- consumo real total por OP;
- consumo real por componente;
- diferenca em kg e percentual;
- status da comparacao;
- indicadores de divergencia ou falta de dados.

## Consumidores

- Manufatura;
- Engenharia de processos;
- Qualidade;
- PCP;
- Gestao industrial.

## Regras Principais

- A OP e a chave logica de correlacao entre Motan, SAP e INJET.
- A janela da OP no Motan e derivada da tag `svOrderNumber`.
- O consumo real e calculado a partir dos deltas positivos dos acumuladores do Motan.
- O consumo planejado vem dos componentes SAP incluidos na regra de resina/material.
- O Fabric deve receber outputs curados e incrementais, nao o raw OPC UA completo por padrao.

## Contrato Relacionado

```text
contracts/data-products/manufacturing/manufacturing-dosage-control.yaml
```

## Status

Draft. Regras, tolerancias, SLAs e criterios de alerta ainda precisam ser validados com manufatura.
