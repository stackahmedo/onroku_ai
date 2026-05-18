$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\Transcript AI V3.lnk")
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-WindowStyle Hidden -Command `"Set-Location 'i:\smart_grid_home\projects\transcript_ai_v2'; .\start_prod.bat`""
$Shortcut.WorkingDirectory = "i:\smart_grid_home\projects\transcript_ai_v2"
$Shortcut.Description = "Transcript AI V3 - Whisper Large V3 Offline Speech-to-Text"
$Shortcut.Save()
Write-Host "Shortcut created successfully on the Desktop with hidden background execution."
