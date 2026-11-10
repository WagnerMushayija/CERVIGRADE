# Sends the current code to the Azure server and restarts the app. Run it in PowerShell on your laptop:
#
#     .\deploy\update_server.ps1
#
# It packs src\ and deploy\ (not the data, not the models), uploads them, installs any new Python package,
# restarts the service and prints the health check. Users, records and uploaded images on the server are not touched.

param(
    [string]$Ip = "4.222.184.40",
    [string]$Key = "$env:USERPROFILE\Downloads\cervigrade_key.pem",
    [string]$User = "azureuser"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$package = Join-Path $env:TEMP "cervigrade_update.tgz"

Push-Location $repo
tar -czf $package --exclude="__pycache__" --exclude=".pytest_cache" src deploy
Pop-Location

# -F NUL ignores your own ssh config file. The upload sometimes resets at 0%, so it tries up to five times.
$sshOptions = @("-F", "NUL", "-o", "ServerAliveInterval=15", "-i", $Key)
$uploaded = $false
for ($try = 1; $try -le 5 -and -not $uploaded; $try++) {
    scp @sshOptions $package "${User}@${Ip}:~/cervigrade_update.tgz"
    if ($LASTEXITCODE -eq 0) { $uploaded = $true } else { Start-Sleep 3 }
}
if (-not $uploaded) { throw "The upload failed five times. Check that the server is running in the Azure portal." }

$remote = @'
set -e
cd ~/CERVIGRADE
sudo systemctl stop cervigrade
# Remove the old code folders first, so a file deleted on the laptop does not linger on the server.
rm -rf src/app/backend/app
for d in core db models repositories routers schemas services tests; do rm -rf src/app/backend/$d; done
find src/app/backend -maxdepth 1 -name "*.py" -delete
tar -xzf ~/cervigrade_update.tgz -C ~/CERVIGRADE
.venv/bin/pip install -q -r src/app/backend/requirements.txt
sudo sed -i 's/ app\.main:app/ main:app/' /etc/systemd/system/cervigrade.service
sudo systemctl daemon-reload
sudo systemctl start cervigrade
echo "Waiting for the models to load..."
sleep 75
curl -s localhost:8000/health | head -c 500; echo
'@
$remote = $remote -replace "`r", ""
ssh @sshOptions "${User}@${Ip}" $remote
Write-Host ""
Write-Host "Done. The app is at http://${Ip}:8000/app  (look for using_real_model: true above)"
