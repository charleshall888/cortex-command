# Signal WezTerm to trigger visual bell
# Creates a signal file that WezTerm watches and responds to
New-Item -Path "$env:USERPROFILE\.claude\notify-bell" -ItemType File -Force | Out-Null
