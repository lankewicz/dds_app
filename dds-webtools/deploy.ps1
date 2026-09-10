param(
    [ValidateSet("1", "2", "3", "4", "0")]
    [string]$Target
)

$Project = "dds-treinamentos"
$SourceDirectory = $PSScriptRoot
$Region = "us-central1"
$ServiceAccount = "dds-admin-sa@$Project.iam.gserviceaccount.com"
$ImageTag = Get-Date -Format "yyyyMMdd-HHmmss"
$Image = "gcr.io/$Project/dds-webtools:$ImageTag"
$AdminService = "dds-admin-site"
$SyncService = "rotalog-sync"
$DailyJob = "rotalog-daily-archive"
$SyncUrl = "https://$SyncService-1014678273143.$Region.run.app"
$Secrets = "ADMIN_PASSWORD=DDS_ADMIN_PASSWORD:latest,APP_SECRET_KEY=DDS_APP_SECRET_KEY:latest,ROTALOG_USUARIO=ROTALOG_USUARIO:latest,ROTALOG_SENHA=ROTALOG_SENHA:latest"
$SyncEnvFile = Join-Path $env:TEMP "dds-sync-env-$ImageTag.yaml"

function Assert-LastCommand([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "Falha em: $Step" }
}

function Show-DeployMenu {
    Write-Host ""
    Write-Host "Deploy DDS" -ForegroundColor Cyan
    Write-Host "1 - Site e Monitor"
    Write-Host "2 - Serviço de raspagem Rotalog e agendas"
    Write-Host "3 - Coleta diária Rotalog e agenda 04:30"
    Write-Host "4 - Todos"
    Write-Host "0 - Sair"
    return Read-Host "Escolha uma opção"
}

function Build-Image {
    Write-Host "Construindo $Image" -ForegroundColor Cyan
    gcloud builds submit --tag=$Image --project=$Project $SourceDirectory
    Assert-LastCommand "Cloud Build"
}

function Deploy-Admin {
    Write-Host "Atualizando $AdminService" -ForegroundColor Cyan
    gcloud run deploy $AdminService `
        --image=$Image `
        --region=$Region `
        --project=$Project `
        --memory=1Gi `
        --cpu=1 `
        --timeout=900 `
        --min-instances=1 `
        --max-instances=1 `
        --concurrency=1 `
        --no-cpu-throttling `
        --service-account=$ServiceAccount `
        --env-vars-file="$SourceDirectory/env.yaml" `
        --set-secrets=$Secrets
    Assert-LastCommand "deploy do site"
}

function Set-SchedulerJob([string]$Name, [string]$Schedule) {
    gcloud scheduler jobs describe $Name --location=$Region --project=$Project *> $null
    $Action = if ($LASTEXITCODE -eq 0) { "update" } else { "create" }
    gcloud scheduler jobs $Action http $Name `
        --location=$Region `
        --project=$Project `
        --schedule=$Schedule `
        --time-zone=America/Sao_Paulo `
        --uri="$SyncUrl/api/rotalog/sync-now" `
        --http-method=POST `
        --oidc-service-account-email=$ServiceAccount `
        --oidc-token-audience=$SyncUrl `
        --attempt-deadline=900s `
        --max-retry-attempts=0
    Assert-LastCommand "configurar Scheduler $Name"
    gcloud scheduler jobs resume $Name --location=$Region --project=$Project
    Assert-LastCommand "ativar Scheduler $Name"
}

function Deploy-Sync {
    Get-Content -LiteralPath (Join-Path $SourceDirectory "env.yaml") | Set-Content -LiteralPath $SyncEnvFile -Encoding utf8
    Add-Content -LiteralPath $SyncEnvFile -Value 'ROTALOG_SYNC_ENDPOINT_IAM_ONLY: "true"' -Encoding utf8
    Write-Host "Atualizando $SyncService" -ForegroundColor Cyan
    gcloud run deploy $SyncService `
        --image=$Image `
        --region=$Region `
        --project=$Project `
        --memory=1Gi `
        --cpu=1 `
        --timeout=900 `
        --min-instances=0 `
        --max-instances=1 `
        --concurrency=2 `
        --cpu-throttling `
        --service-account=$ServiceAccount `
        --env-vars-file=$SyncEnvFile `
        --set-secrets=$Secrets `
        --no-allow-unauthenticated
    Assert-LastCommand "deploy do serviço Rotalog"
    gcloud run services add-iam-policy-binding $SyncService `
        --region=$Region `
        --project=$Project `
        --member="serviceAccount:$ServiceAccount" `
        --role=roles/run.invoker
    Assert-LastCommand "permissão do Scheduler"
    Set-SchedulerJob "rotalog-sync-0600-1759-5m" "*/5 6-17 * * *"
    Set-SchedulerJob "rotalog-sync-1800-2159-10m" "*/10 18-21 * * *"
    Set-SchedulerJob "rotalog-sync-2200-0559-30m" "*/30 22-23,0-5 * * *"
}

function Deploy-Daily {
    Write-Host "Atualizando $DailyJob" -ForegroundColor Cyan
    gcloud run jobs describe $DailyJob --region=$Region --project=$Project *> $null
    $Action = if ($LASTEXITCODE -eq 0) { "update" } else { "deploy" }
    gcloud run jobs $Action $DailyJob `
        --image=$Image `
        --region=$Region `
        --project=$Project `
        --command=python `
        --args=rotalog_daily_archive_job.py `
        --memory=1Gi `
        --cpu=1 `
        --task-timeout=1800s `
        --max-retries=2 `
        --service-account=$ServiceAccount `
        --set-env-vars="DDS_BUCKET_NAME=dds-treinamentos.firebasestorage.app,ROTALOG_DAILY_ARCHIVE_PREFIX=dados,ROTALOG_EMPRESA=ChicoEletro,DDS_TIMEZONE=America/Sao_Paulo" `
        --set-secrets="ROTALOG_USUARIO=ROTALOG_USUARIO:latest,ROTALOG_SENHA=ROTALOG_SENHA:latest"
    Assert-LastCommand "deploy da coleta diária"
    gcloud scheduler jobs resume rotalog-daily-archive-0430 --location=$Region --project=$Project
    Assert-LastCommand "ativar coleta diária"
}

if (-not $Target) { $Target = Show-DeployMenu }
if ($Target -eq "0") { Write-Host "Deploy cancelado."; exit 0 }

try {
    Build-Image
    switch ($Target) {
        "1" { Deploy-Admin }
        "2" { Deploy-Sync }
        "3" { Deploy-Daily }
        "4" { Deploy-Admin; Deploy-Sync; Deploy-Daily }
    }
    Write-Host "Deploy concluído: $Image" -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $SyncEnvFile) { Remove-Item -LiteralPath $SyncEnvFile -Force }
}
