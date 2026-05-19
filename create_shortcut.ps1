$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")

# Clean up legacy shortcuts
$OldShortcuts = @(
    "$DesktopPath\Transcript V4.lnk",
    "$DesktopPath\Transcript V3.lnk",
    "$DesktopPath\Transcript V2.lnk",
    "$DesktopPath\Transcript AI V3.lnk",
    "$DesktopPath\Transcript AI V2.lnk"
)
foreach ($old in $OldShortcuts) {
    if (Test-Path $old) {
        Remove-Item $old -Force
    }
}

# Create new Onroku AI shortcut
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\Onroku AI.lnk")
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-ExecutionPolicy Bypass -WindowStyle Hidden -Command `"Set-Location 'i:\smart_grid_home\projects\transcript_ai_v2'; .\start_prod.bat`""
$Shortcut.WorkingDirectory = "i:\smart_grid_home\projects\transcript_ai_v2"
$Shortcut.IconLocation = "$($Shortcut.WorkingDirectory)\public\icon.ico"
$Shortcut.Description = "Onroku AI V6.0 - Whisper Large V3 Offline Speech-to-Text"
$Shortcut.Save()

Write-Host "Shortcut 'Onroku AI' created successfully on the Desktop with hidden background execution."
