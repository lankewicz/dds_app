param(
    [ValidateSet("1", "0")]
    [string]$Target
)

$Project = "dds-treinamentos"
$SourceDirectory = $PSScriptRoot
$Region = "us-central1"
$ServiceAccount = "dds-admin-sa@$Project.iam.gserviceaccount.com"
$ImageTag = Get-Date -Format "yyyyMMdd-HHmmss"
$Image = "gcr.io/$Project/dds-webtools:$ImageTag"
$AdminService = "dds-admin-site"
$Secrets = "ADMIN_PASSWORD=DDS_ADMIN_PASSWORD:latest,APP_SECRET_KEY=DDS_APP_SECRET_KEY:latest"

function Assert-LastCommand([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "Falha em: $Step" }
}

function Show-DeployMenu {
    Write-Host ""
    Write-Host "Deploy DDS" -ForegroundColor Cyan
    Write-Host "1 - Site e Monitor"
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
    $AdminSecrets = $Secrets
    gcloud secrets describe DDS_TAILSCALE_OAUTH_SECRET --project=$Project *> $null
    if ($LASTEXITCODE -eq 0) {
        $AdminSecrets += ",TAILSCALE_OAUTH_SECRET=DDS_TAILSCALE_OAUTH_SECRET:latest"
    } else {
        gcloud secrets describe DDS_TAILSCALE_AUTHKEY --project=$Project *> $null
        if ($LASTEXITCODE -eq 0) {
            $AdminSecrets += ",TAILSCALE_AUTHKEY=DDS_TAILSCALE_AUTHKEY:latest"
        } else {
            Write-Host "Credencial Tailscale ausente: o site usará o fallback Firebase." -ForegroundColor Yellow
        }
    }
    gcloud run deploy $AdminService `
        --image=$Image `
        --region=$Region `
        --project=$Project `
        --memory=1Gi `
        --cpu=1 `
        --timeout=900 `
        --min=0 `
        --min-instances=0 `
        --max-instances=1 `
        --concurrency=1 `
        --cpu-throttling `
        --service-account=$ServiceAccount `
        --env-vars-file="$SourceDirectory/env.yaml" `
        --set-secrets=$AdminSecrets
    Assert-LastCommand "deploy do site"
}

if (-not $Target) { $Target = Show-DeployMenu }
if ($Target -eq "0") { Write-Host "Deploy cancelado."; exit 0 }

Build-Image
Deploy-Admin
Write-Host "Deploy concluído: $Image" -ForegroundColor Green
