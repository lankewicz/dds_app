# Script para limpeza de revisões antigas do Cloud Run
# Mantém apenas as N revisões mais recentes para evitar poluição e custo de storage de imagens.

$SERVICE_NAME = "dds-admin-site"
$REGION = "us-central1"
$PROJECT = "dds-treinamentos"
$KEEP_COUNT = 10

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   Limpando Revisões Antigas: $SERVICE_NAME    " -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# 1. Obtém a lista de todas as revisões, ordenadas da mais nova para a mais antiga
Write-Host "Buscando revisões no Google Cloud..."
$revisions = gcloud run revisions list `
    --service $SERVICE_NAME `
    --region $REGION `
    --project $PROJECT `
    --format="value(metadata.name)" `
    --sort-by="~metadata.creationTimestamp"

if ($null -eq $revisions -or $revisions.Count -le $KEEP_COUNT) {
    Write-Host "Poucas revisões encontradas ($($revisions.Count)). Nada para limpar." -ForegroundColor Yellow
    exit 0
}

# 2. Seleciona as revisões para apagar (pula as N mais novas)
$toDelete = $revisions | Select-Object -Skip $KEEP_COUNT

Write-Host "Total de revisões: $($revisions.Count)"
Write-Host "Mantendo as $KEEP_COUNT mais recentes."
Write-Host "Apagando $($toDelete.Count) revisões antigas..." -ForegroundColor Yellow

# 3. Executa a deleção
$count = 0
foreach ($rev in $toDelete) {
    $count++
    Write-Host "[$count/$($toDelete.Count)] Removendo: $rev ..." -NoNewline
    gcloud run revisions delete $rev --region $REGION --project $PROJECT --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host " [OK]" -ForegroundColor Green
    } else {
        Write-Host " [ERRO]" -ForegroundColor Red
    }
}

Write-Host "`n===============================================" -ForegroundColor Cyan
Write-Host "   Limpeza concluída com sucesso!              " -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Cyan
