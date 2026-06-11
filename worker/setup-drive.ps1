param(
    [string]$RemoteName = "gdrive",
    [string]$Folder = "Family EPUB Library"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    Write-Host "rclone is not installed. Installing with winget..."
    winget install Rclone.Rclone --exact --accept-package-agreements --accept-source-agreements
}

if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    throw "rclone was not found on PATH after install. Open a new PowerShell window and run this script again."
}

Write-Host "Checking rclone remote '$RemoteName'..."
$remotes = rclone listremotes
if ($remotes -notcontains "$RemoteName`:") {
    Write-Host "Remote '$RemoteName' is not configured yet."
    Write-Host "Use 'n' for new remote, name it '$RemoteName', choose Google Drive, and approve access in your browser."
    rclone config
}

Write-Host "Creating/checking Drive folder '$Folder'..."
rclone mkdir "$RemoteName`:$Folder"
rclone lsd "$RemoteName`:$Folder"

Write-Host ""
Write-Host "Drive destination is ready:"
Write-Host "$RemoteName`:$Folder"
