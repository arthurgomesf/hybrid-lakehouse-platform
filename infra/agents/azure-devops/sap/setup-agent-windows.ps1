#!/usr/bin/env powershell
# Setup do agente self-hosted do Azure DevOps (Windows).
# Espera: AZP_URL, AZP_TOKEN, AZP_POOL, AZP_AGENT_NAME (opcional).
$ErrorActionPreference = "Stop"

$url = $env:AZP_URL
$token = $env:AZP_TOKEN
$pool = $env:AZP_POOL
$agentName = $env:AZP_AGENT_NAME
if (-not $agentName) { $agentName = $env:COMPUTERNAME }

if (-not $url -or -not $token -or -not $pool) {
    Write-Error "AZP_URL, AZP_TOKEN e AZP_POOL sao obrigatorios."
    exit 1
}

$root = "C:\azdo-agent"
New-Item -ItemType Directory -Force -Path $root | Out-Null

$latest = (Invoke-RestMethod "https://api.github.com/repos/microsoft/azure-pipelines-agent/releases/latest").tag_name -replace '^v', ''
$zip = "$root\agent.zip"
Invoke-WebRequest -Uri "https://vstsagentpackage.azureedge.net/agent/$latest/vsts-agent-win-x64-$latest.zip" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $root -Force
Remove-Item $zip -Force

Set-Location $root

./config.cmd --unattended `
    --agent "$agentName" `
    --url "$url" `
    --auth PAT `
    --token "$token" `
    --pool "$pool" `
    --replace `
    --acceptTeeEula

Write-Host "Agente registrado com sucesso. Inicie com: C:\azdo-agent\run.cmd"