# Motan Azure DevOps Agent

Self-hosted Azure DevOps agent used to run source-to-landing ingestion jobs near Motan data sources.

## Runtime Location

Expected VM path:

```text
/opt/azdo-agent-docker
```

## Files

- `Dockerfile`: Ubuntu-based agent image with Python, Git and AzCopy.
- `start.sh`: downloads and registers the latest Azure Pipelines agent.
- `docker-compose.yml`: runs one constrained agent container.
- `.env.example`: required local variables without secrets.

## Local Setup

Create a local `.env` from `.env.example` and fill the real values on the VM only:

```bash
cp .env.example .env
chmod 600 .env
docker compose up -d --build
```

Do not commit `.env` or tokens.

## Validation

```bash
docker compose ps
docker logs -f azdo-agent-motan-01
```

Expected Azure DevOps status:

```text
motan-agent-01 Online / Idle
```
