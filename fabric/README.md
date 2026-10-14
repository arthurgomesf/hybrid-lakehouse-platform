# Fabric

Itens do lakehouse no formato da Git Integration do Microsoft Fabric, com IDs de
workspace, lakehouse e conexao trocados por placeholders (`<workspace-id>`,
`<storage-account>`, ...).

| Pasta | Conteudo |
|---|---|
| `finance/` | `lh_finance` (shortcut `Files/sap`), `nb_bronze_sap`, `nb_silver_finance`, `pl_finance_sap` |
| `manufacturing/` | `lh_manufacturing` (shortcut `Files/motan`), Bronze/Silver/Gold, `pl_manufacturing_dosage_control`, semantic model |

Os notebooks aplicam as mesmas regras de `local/medallion.py` (que e o que os
testes cobrem): leitura por manifest, ordem por `_run_started_at`, tabela de
controle e MERGE condicional.

Para usar em um workspace real: conectar o workspace a uma branch pela Git
Integration, ajustar os shortcuts para a sua conta de storage e trocar os
placeholders das pipelines pelos IDs dos notebooks.
