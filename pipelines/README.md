# Pipelines

- `exporters/source_to_landing.py`: exportador generico (HANA, Postgres, DuckDB).
- `sources/<fonte>/datasets.yaml` + `sources/<fonte>/sql/*.sql`: configuracao e SQL por fonte.
- `azure-devops/*.yml`: agendamento no Azure DevOps (agentes self-hosted).

Detalhes em `docs/architecture/source-to-landing-ingestion.md`.

Credenciais nunca ficam aqui: o pipeline le secret variables do Azure DevOps.
