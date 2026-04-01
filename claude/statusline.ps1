# statusline.ps1 - Claude Code Statusline for Windows
# Ported from cc-statusline v1.4.0 bash script
# Save to: $env:USERPROFILE\.claude\statusline.ps1

# ---- Read JSON input from stdin ----
$inputJson = [Console]::In.ReadToEnd()
try {
    $data = $inputJson | ConvertFrom-Json
} catch {
    Write-Host "Error parsing JSON"
    exit 1
}

# ---- ANSI color helpers ----
$ESC = [char]27
function Color($code) { "$ESC[38;5;${code}m" }
function Reset { "$ESC[0m" }

# Color palette
$dirColor = Color 117      # sky blue
$gitColor = Color 150      # soft green
$modelColor = Color 147    # light purple
$versionColor = Color 180  # soft yellow
$ccVersionColor = Color 249 # light gray
$styleColor = Color 245    # gray
$costColor = Color 228     # soft yellow
$burnColor = Color 209     # orange
$usageColor = Color 117    # sky blue
$rst = Reset

# ---- Extract basic fields ----
$currentDir = if ($data.workspace.current_dir) { $data.workspace.current_dir }
              elseif ($data.cwd) { $data.cwd }
              else { "unknown" }
# Shorten home directory
$currentDir = $currentDir -replace [regex]::Escape($env:USERPROFILE), "~"

$modelName = if ($data.model.display_name) { $data.model.display_name } else { "Claude" }
$modelVersion = $data.model.version
$ccVersion = $data.version
$outputStyle = $data.output_style.name

# ---- Git branch ----
$gitBranch = ""
try {
    $gitBranch = git branch --show-current 2>$null
    if (-not $gitBranch) {
        $gitBranch = git rev-parse --short HEAD 2>$null
    }
} catch { }

# ---- Context window calculation ----
$contextPct = ""
$contextRemainingPct = 0
$contextColor = Color 158  # default mint green

$contextSize = if ($data.context_window.context_window_size) { $data.context_window.context_window_size } else { 200000 }
$usage = $data.context_window.current_usage

if ($usage) {
    $inputTokens = if ($usage.input_tokens) { $usage.input_tokens } else { 0 }
    $cacheCreation = if ($usage.cache_creation_input_tokens) { $usage.cache_creation_input_tokens } else { 0 }
    $cacheRead = if ($usage.cache_read_input_tokens) { $usage.cache_read_input_tokens } else { 0 }
    $currentTokens = $inputTokens + $cacheCreation + $cacheRead

    if ($currentTokens -gt 0) {
        $contextUsedPct = [math]::Floor($currentTokens * 100 / $contextSize)
        $contextRemainingPct = 100 - $contextUsedPct
        if ($contextRemainingPct -lt 0) { $contextRemainingPct = 0 }
        if ($contextRemainingPct -gt 100) { $contextRemainingPct = 100 }

        # Set color based on remaining
        if ($contextRemainingPct -le 20) {
            $contextColor = Color 203  # coral red
        } elseif ($contextRemainingPct -le 40) {
            $contextColor = Color 215  # peach
        } else {
            $contextColor = Color 158  # mint green
        }

        $contextPct = "$contextRemainingPct%"
    }
}

# ---- Cost and tokens ----
$costUsd = $data.cost.total_cost_usd
$durationMs = $data.cost.total_duration_ms
$totalInputTokens = if ($data.context_window.total_input_tokens) { $data.context_window.total_input_tokens } else { 0 }
$totalOutputTokens = if ($data.context_window.total_output_tokens) { $data.context_window.total_output_tokens } else { 0 }
$totTokens = $totalInputTokens + $totalOutputTokens

$costPerHour = $null
if ($costUsd -and $durationMs -and $durationMs -gt 0) {
    $costPerHour = [math]::Round($costUsd / ($durationMs / 3600000), 2)
}

# ---- Progress bar helper ----
function ProgressBar($pct, $width = 10) {
    if ($pct -lt 0) { $pct = 0 }
    if ($pct -gt 100) { $pct = 100 }
    $filled = [math]::Floor($pct * $width / 100)
    $empty = $width - $filled
    ("=" * $filled) + ("-" * $empty)
}

# ---- Render statusline ----
# Line 1: Core info
$line1 = "📁 $dirColor$currentDir$rst"
if ($gitBranch) {
    $line1 += "  🌿 $gitColor$gitBranch$rst"
}
$line1 += "  🤖 $modelColor$modelName$rst"
if ($modelVersion) {
    $line1 += "  🏷️ $versionColor$modelVersion$rst"
}
if ($ccVersion) {
    $line1 += "  📟 ${ccVersionColor}v$ccVersion$rst"
}
if ($outputStyle) {
    $line1 += "  🎨 $styleColor$outputStyle$rst"
}

# Line 2: Context
$line2 = ""
if ($contextPct) {
    $bar = ProgressBar $contextRemainingPct 10
    $line2 = "🧠 ${contextColor}Context Remaining: $contextPct [$bar]$rst"
} else {
    $line2 = "🧠 ${contextColor}Context Remaining: TBD$rst"
}

# Line 3: Cost and usage
$line3 = ""
if ($costUsd -and $costUsd -match '^\d') {
    $costFormatted = "{0:F2}" -f [double]$costUsd
    if ($costPerHour) {
        $cphFormatted = "{0:F2}" -f $costPerHour
        $line3 = "💰 $costColor`$$costFormatted$rst ($burnColor`$$cphFormatted/h$rst)"
    } else {
        $line3 = "💰 $costColor`$$costFormatted$rst"
    }
}
if ($totTokens -and $totTokens -gt 0) {
    if ($line3) {
        $line3 += "  📊 $usageColor$totTokens tok$rst"
    } else {
        $line3 = "📊 $usageColor$totTokens tok$rst"
    }
}

# Output
Write-Host $line1
if ($line2) { Write-Host $line2 }
if ($line3) { Write-Host $line3 }
