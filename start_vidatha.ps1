
# ============================================================
# VIDATHA BACKEND - AUTOMATIC STARTUP SCRIPT
# ============================================================

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# 1. Project configuration
# ------------------------------------------------------------
$ProjectRoot = "F:\MeetNotes\MeetNotes"
$BackendDir  = Join-Path $ProjectRoot "backend"
$PythonExe   = Join-Path $BackendDir ".venv311\Scripts\python.exe"

# ------------------------------------------------------------
# 2. SSL certificate configuration
# ------------------------------------------------------------
$CertDir  = "C:\Users\Cdac\GPU_MeetMIND_certs"
$KeyFile  = Join-Path $CertDir "meetmind-key.pem"
$CertFile = Join-Path $CertDir "meetmind-cert.pem"

# ------------------------------------------------------------
# 3. Logging configuration
# ------------------------------------------------------------
$LogDir = Join-Path $ProjectRoot "logs"

$LogFile    = Join-Path $LogDir "vidatha-startup.log"
$StdoutLog  = Join-Path $LogDir "vidatha-stdout.log"
$StderrLog  = Join-Path $LogDir "vidatha-stderr.log"

# Create log directory if it does not exist
New-Item -ItemType Directory -Path $LogDir -Force |
    Out-Null

# ------------------------------------------------------------
# 4. Logging function
# ------------------------------------------------------------
function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"

    Add-Content -LiteralPath $LogFile -Value $LogMessage
    Write-Host $LogMessage
}

Write-Log "============================================================"
Write-Log "Vidatha startup script launched."

# ------------------------------------------------------------
# 5. Validate required files
# ------------------------------------------------------------
$RequiredFiles = @(
    $PythonExe,
    $KeyFile,
    $CertFile
)

foreach ($FilePath in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        Write-Log "ERROR: Required file not found: $FilePath"
        exit 1
    }
}

Write-Log "Python executable verified."
Write-Log "SSL key and certificate verified."

# ------------------------------------------------------------
# 6. Set working directory
# ------------------------------------------------------------
Set-Location -LiteralPath $BackendDir

Write-Log "Backend directory: $BackendDir"

# ------------------------------------------------------------
# 7. Check whether port 8100 is already occupied
# ------------------------------------------------------------
$ExistingListener = Get-NetTCPConnection `
    -LocalPort 8100 `
    -State Listen `
    -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($ExistingListener) {
    $ExistingPID = $ExistingListener.OwningProcess

    Write-Log "Port 8100 already has a listener (PID $ExistingPID)."
    Write-Log "Skipping startup to prevent a duplicate server."

    exit 0
}

Write-Log "Port 8100 is available."

# ------------------------------------------------------------
# 8. Configure Uvicorn arguments
# ------------------------------------------------------------
$UvicornArgs = @(
    "-u",
    "-m", "uvicorn",
    "app:app",
    "--host", "0.0.0.0",
    "--port", "8100",
    "--ssl-keyfile", $KeyFile,
    "--ssl-certfile", $CertFile
)

# --reload is intentionally disabled for stable startup.

# ------------------------------------------------------------
# 9. Prepare separate output log files
# ------------------------------------------------------------
try {
    # Create or clear the logs for this startup attempt
    Set-Content -LiteralPath $StdoutLog -Value ""
    Set-Content -LiteralPath $StderrLog -Value ""

    Write-Log "Starting Uvicorn as a separate process."

    # --------------------------------------------------------
    # 10. Launch Uvicorn
    # --------------------------------------------------------
    $Process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $UvicornArgs `
        -WorkingDirectory $BackendDir `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru

    Write-Log "Uvicorn launch requested. PID: $($Process.Id)"
}
catch {
    Write-Log "ERROR launching Uvicorn: $($_.Exception.Message)"
    exit 1
}

# ------------------------------------------------------------
# 11. Wait for the server to start
# ------------------------------------------------------------
$Ready = $false

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1

    # Check whether Uvicorn exited during startup
    $Process.Refresh()

    if ($Process.HasExited) {
        Write-Log "ERROR: Uvicorn exited with code $($Process.ExitCode)."

        if (Test-Path -LiteralPath $StdoutLog) {
            Add-Content -LiteralPath $LogFile `
                -Value "`n--- Uvicorn standard output ---"

            Get-Content -LiteralPath $StdoutLog -Tail 30 |
                Add-Content -LiteralPath $LogFile
        }

        if (Test-Path -LiteralPath $StderrLog) {
            Add-Content -LiteralPath $LogFile `
                -Value "`n--- Uvicorn standard error ---"

            Get-Content -LiteralPath $StderrLog -Tail 30 |
                Add-Content -LiteralPath $LogFile
        }

        exit 1
    }

    $Listener = Get-NetTCPConnection `
        -LocalPort 8100 `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($Listener) {
        Write-Log "Port 8100 is listening. PID: $($Listener.OwningProcess)"
        $Ready = $true
        break
    }
}

# ------------------------------------------------------------
# 12. Final startup result
# ------------------------------------------------------------
if ($Ready) {
    Write-Log "Vidatha backend startup check passed."
    Write-Log "HTTPS endpoint: https://localhost:8100/docs"
    Write-Log "Standard output log: $StdoutLog"
    Write-Log "Standard error log: $StderrLog"
    Write-Log "Startup script completed successfully."
    exit 0
}
else {
    Write-Log "ERROR: No listener detected on port 8100 after 30 seconds."
    Write-Log "Check the Uvicorn stdout and stderr log files."

    if (Test-Path -LiteralPath $StdoutLog) {
        Get-Content -LiteralPath $StdoutLog -Tail 30 |
            Add-Content -LiteralPath $LogFile
    }

    if (Test-Path -LiteralPath $StderrLog) {
        Get-Content -LiteralPath $StderrLog -Tail 30 |
            Add-Content -LiteralPath $LogFile
    }

    exit 1
}

