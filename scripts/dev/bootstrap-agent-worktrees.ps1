$ErrorActionPreference = "Stop"

try {
    $repoRoot = (git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    throw "Run this script from inside a Workflo Git checkout."
}
if (-not $repoRoot) { throw "Run this script from inside a Workflo Git checkout." }

$remote = if ($env:WORKFLO_REMOTE) { $env:WORKFLO_REMOTE } else { "origin" }
git -C $repoRoot remote get-url $remote | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Git remote '$remote' was not found." }

git -C $repoRoot fetch $remote --prune
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }

$parentDir = Split-Path -Parent $repoRoot
$worktreeRoot = if ($env:WORKFLO_WORKTREE_ROOT) {
    $env:WORKFLO_WORKTREE_ROOT
} else {
    Join-Path $parentDir ".workflo-worktrees"
}
New-Item -ItemType Directory -Force -Path $worktreeRoot | Out-Null

$specs = @(
    @{ Branch = "agent/deepseek-native-cli-runner"; Folder = "deepseek-native-cli-runner" },
    @{ Branch = "agent/glm-cli-connectors-distribution"; Folder = "glm-cli-connectors-distribution" },
    @{ Branch = "agent/minimax-sandbox-security-qa"; Folder = "minimax-sandbox-security-qa" },
    @{ Branch = "agent/gemini-dashboard-frontend"; Folder = "gemini-dashboard-frontend" },
    @{ Branch = "agent/gpt6-luna-backend-platform"; Folder = "gpt6-luna-backend-platform" }
)

foreach ($spec in $specs) {
    $branch = $spec.Branch
    $target = Join-Path $worktreeRoot $spec.Folder

    git -C $repoRoot show-ref --verify --quiet "refs/remotes/$remote/$branch"
    if ($LASTEXITCODE -ne 0) { throw "Missing remote branch: $remote/$branch" }

    if (Test-Path $target) {
        $actualRoot = (git -C $target rev-parse --show-toplevel 2>$null)
        $actualBranch = (git -C $target branch --show-current 2>$null)
        if ($LASTEXITCODE -eq 0 -and $actualRoot -and
            ([IO.Path]::GetFullPath($actualRoot.Trim()) -eq [IO.Path]::GetFullPath($target)) -and
            ($actualBranch.Trim() -eq $branch)) {
            Write-Host "Already configured: $target ($branch)"
            continue
        }
        throw "Refusing to overwrite non-matching existing path: $target"
    }

    git -C $repoRoot show-ref --verify --quiet "refs/heads/$branch"
    if ($LASTEXITCODE -eq 0) {
        git -C $repoRoot worktree add $target $branch
    } else {
        git -C $repoRoot worktree add --track -b $branch $target "$remote/$branch"
    }
    if ($LASTEXITCODE -ne 0) { throw "Failed to create worktree for $branch" }
    Write-Host "Created: $target ($branch)"
}

Write-Host ""
git -C $repoRoot worktree list
