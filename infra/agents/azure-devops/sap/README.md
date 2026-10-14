# Agente Azure DevOps Para O SAP (Windows)

Agente self-hosted que roda o exportador perto do SAP, dentro da rede interna.

## Requisitos

- **Maquina sempre ligada** (VM ou servidor). Um agente em estacao de trabalho
  faz o agendamento acumular execucoes na fila sempre que a maquina desliga.
- Driver ODBC do SAP HANA instalado e um DSN apontando para o servidor HANA.
- Python 3.10+ e AzCopy.
- Acesso de rede ao HANA (host/porta do DSN) e ao ADLS.

## Variaveis secretas esperadas no Azure DevOps

Configurar como secret variables ou variable group ligado ao Key Vault, nunca no
repositorio:

- `HANA_CONNECTION_STRING` (ex.: `DSN=<dsn>;UID=<usuario>;PWD=<senha>`)
- `AZURE_STORAGE_LANDING_URL`
- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`

## Registro do agente

```powershell
$env:AZP_URL = "https://dev.azure.com/<org>"
$env:AZP_TOKEN = "<PAT com escopo Agent Pools (read, manage)>"
$env:AZP_POOL = "sap-windows-agents"
$env:AZP_AGENT_NAME = "sap-agent-01"
.\setup-agent-windows.ps1
```

O pool do pipeline YAML deve ser o mesmo usado aqui (`sap-windows-agents`).
O PAT so e usado no registro; depois disso pode ser revogado.

## Validacao

O agente deve aparecer como `Online / Idle` no Azure DevOps. Rode o pipeline
manualmente uma vez antes de habilitar o agendamento.
