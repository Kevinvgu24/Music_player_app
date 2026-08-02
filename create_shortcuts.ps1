$desktop = [Environment]::GetFolderPath('Desktop')
$exePath = "C:\Users\Phant\Music\Music_player_app\dist\PlaylistOffline.exe"
$vbsPath = "C:\Users\Phant\Music\Music_player_app\run_playlist_app.vbs"

$ws = New-Object -ComObject WScript.Shell

# 1. Desktop shortcut targeting standalone executable directly
$sc = $ws.CreateShortcut("$desktop\Playlist Offline.lnk")
$sc.TargetPath = $exePath
$sc.WorkingDirectory = "C:\Users\Phant\Music\Music_player_app\dist"
$sc.IconLocation = "$exePath,0"
$sc.Save()

# 2. Silent VBScript launcher shortcut backup
$iconPath = "C:\Users\Phant\Music\Music_player_app\APP\app_icon.ico"
$sc2 = $ws.CreateShortcut("$desktop\Playlist Offline (Silent).lnk")
$sc2.TargetPath = "wscript.exe"
$sc2.Arguments = "`"$vbsPath`""
$sc2.WorkingDirectory = "C:\Users\Phant\Music\Music_player_app"
$sc2.IconLocation = "$iconPath,0"
$sc2.Save()

Write-Host "Desktop shortcuts created successfully at: $desktop"
