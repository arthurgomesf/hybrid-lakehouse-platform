# Contracts

Data Contracts da plataforma, em YAML (padrao em `docs/standards/data-contracts.md`).

- `sources/<fonte>/<contrato>.yaml`: contratos de fonte;
- `data-products/<dominio>/<contrato>.yaml`: contratos de Data Product.

Os contratos nao sao so documentacao: o exportador le `schema.fields` (ou a secao
indicada em `contract_schema`) para gravar o Parquet com os tipos corretos e falha
se a query devolver colunas diferentes.

| Contrato | Dataset | Carga |
|---|---|---|
| `sources/sap/sap-purchase-invoices.yaml` | notas de entrada (OPCH) | incremental por `UpdateDate` |
| `sources/sap/sap-return-transfers.yaml` | pedidos de transferencia + transferencias | full |
| `sources/sap/sap-service-invoices.yaml` | notas de servico com retencoes, duas empresas | full |
| `sources/sap/sap-production-orders.yaml` | OPs e componentes (cache da Service Layer) | incremental |
| `sources/motan/*.yaml` | janelas de OP, consumo, leituras brutas (on-prem) | incremental |
| `sources/injet/*.yaml` | OP corrente por maquina | referencia |
| `data-products/manufacturing/manufacturing-dosage-control.yaml` | consumo real x planejado por OP | Gold |
