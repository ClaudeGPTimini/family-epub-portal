param(
    [string]$SiteDir = "..\site",
    [string]$PublishRepoDir = "..\..\..\work\family-epub-portal-publish",
    [string]$Message = "Update library data"
)

$ErrorActionPreference = "Stop"

$sitePath = Resolve-Path $SiteDir
$repoPath = Resolve-Path $PublishRepoDir

Copy-Item -Path (Join-Path $sitePath "data\*.json") -Destination (Join-Path $repoPath "data") -Force

Push-Location $repoPath
try {
    git status --short
    git add data/*.json
    $changes = git diff --cached --name-only
    if (-not $changes) {
        Write-Host "No site data changes to publish."
        exit 0
    }
    git commit -m $Message
    git push
} finally {
    Pop-Location
}
