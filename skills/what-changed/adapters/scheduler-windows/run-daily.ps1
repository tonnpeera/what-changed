<#
Run what-changed once, unattended, on Windows, with Claude Code (`claude -p`).
Schedule it with Task Scheduler (see ../README.md). Not tested on Windows yet; it follows
../scheduler-cron/run-daily.sh, which is tested on macOS.

  -Project       folder that holds uptodate/ (or set WHAT_CHANGED_PROJECT)
  -FetchDomains  hosts the agent may fetch besides the ones in topics.yaml, comma-separated,
                 "*" = any host (optional; or set WHAT_CHANGED_FETCH_DOMAINS)
  -Claude        full path to claude.exe (optional; or set WHAT_CHANGED_CLAUDE;
                 default: %USERPROFILE%\.local\bin\claude.exe, else the first claude on PATH)
  -Python        Python 3.11 or later (optional; or set WHAT_CHANGED_PYTHON; default: py -3, then python)
  -ApproveTopics approve the topics.yaml you reviewed, named by the first 12 characters of its hash,
                 then exit. Runs stop while topics.yaml differs from the approved copy; the stop
                 message shows what changed and the exact command.

How it differs from run-daily.sh: the agent gets no shell at all. This script runs the skill's
scripts itself: precheck.py and fingerprint.py before the agent (the fingerprints go into the
prompt, so the next precheck compares like with like), and log_run.py (the runs.log line, stamped
from the system clock), check_ledger.py and verify_quotes.py after it. The agent can read the store
and the skill, edit only the ledgers and digests, and fetch only the allowed hosts.

When it cannot finish (claude missing or too old, no source reachable, the agent failed or wrote
no digest, the ledger check failed) it says why, writes the reason to <state dir>\<today>-error.txt,
which the catch-up hook shows in your next session, and does not count the day as done.
#>
param(
  [string]$Project = $env:WHAT_CHANGED_PROJECT,
  [string]$FetchDomains = $env:WHAT_CHANGED_FETCH_DOMAINS,
  [string]$Claude = $env:WHAT_CHANGED_CLAUDE,
  [string]$Python = $env:WHAT_CHANGED_PYTHON,
  [string]$ApproveTopics = ''
)
# Exit codes of native commands are checked one by one below. 'Stop' would also turn any line a
# native command writes to stderr into a terminating error on Windows PowerShell 5.1.
$ErrorActionPreference = 'Continue'
$ClaudeMin = '2.1.248'   # --restricted

function Exit-Early([string]$Why, [int]$Code) { [Console]::Error.WriteLine("what-changed: $Why"); exit $Code }

if (-not $Project) { Exit-Early 'set -Project (or WHAT_CHANGED_PROJECT) to the folder that contains uptodate\' 2 }
$RealProject = (Resolve-Path -LiteralPath $Project -ErrorAction SilentlyContinue).Path
if (-not $RealProject) { Exit-Early "no folder at $Project" 2 }
$Skill = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Store = Join-Path $RealProject 'uptodate'
$Today = Get-Date -Format 'yyyy-MM-dd'

$UptodatePrefix = (Join-Path $RealProject 'uptodate') + [IO.Path]::DirectorySeparatorChar
if (($Skill + [IO.Path]::DirectorySeparatorChar).StartsWith($UptodatePrefix, [StringComparison]::OrdinalIgnoreCase)) {
  Exit-Early 'refusing: the skill folder is inside uptodate\, which the agent can edit; install it elsewhere' 2
}

# Python: the launcher (py -3) comes with the python.org installer; -I keeps the current folder
# off the import path, so a json.py dropped in the project cannot run as you.
if ($Python) { $Py = @($Python -split ' ') }
elseif (Get-Command py -ErrorAction SilentlyContinue) { $Py = @('py', '-3') }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $Py = @('python') }
else { Exit-Early 'Python 3 not found: install it from python.org or set -Python' 2 }
$PyArgs = @($Py | Select-Object -Skip 1) + @('-I')
function Invoke-Py { param([string[]]$Arguments) & $Py[0] @PyArgs @Arguments }
# The skill's scripts need Python 3.11 or later. (Single quotes only: see the note on -c below.)
Invoke-Py @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)')
if ($LASTEXITCODE -ne 0) { Exit-Early "$($Py -join ' ') is older than Python 3.11: install a newer one from python.org, or set -Python" 2 }

# Logs and the date of the last completed run live outside the project, keyed by the project folder
# (the same key catch_up.py computes).
$StateRoot = if ($env:XDG_STATE_HOME) { $env:XDG_STATE_HOME } else { Join-Path $HOME '.local\state' }
# No double quotes inside -c: Windows PowerShell 5.1 does not escape them for native programs.
# Path.resolve() gives the folder name as stored on disk, the same key catch_up.py computes.
$Key = Invoke-Py @('-c', 'import hashlib, pathlib, sys; print(hashlib.sha256(str(pathlib.Path(sys.argv[1]).resolve()).encode()).hexdigest()[:16])', $RealProject)
if ($LASTEXITCODE -ne 0 -or -not $Key) { Exit-Early "$($Py -join ' ') did not run" 2 }
$LogDir = Join-Path (Join-Path $StateRoot 'what-changed') $Key
$Done = Join-Path (Join-Path $StateRoot 'what-changed') "$Key.last-run"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ErrorFile = Join-Path $LogDir "$Today-error.txt"

function Stop-Run([string]$Why, [int]$Code) {
  [Console]::Error.WriteLine("what-changed: $Why")
  Add-Content -LiteralPath $ErrorFile -Encoding utf8 -Value ("{0} what-changed scheduled run did not finish: {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'), $Why)
  exit $Code
}

if (-not (Test-Path -LiteralPath $Store -PathType Container)) { Stop-Run "no store folder at $Store" 2 }

# topics.yaml decides which hosts precheck and the agent may fetch, and an interactive session can
# edit it. So the scheduled steps never read it: precheck and hosts.py read a copy you approved, kept
# here outside the project. A run stops while topics.yaml differs from that copy, and a run whose
# agent changed it is not counted as done.
$Scripts = Join-Path $Skill 'scripts'
$Topics = Join-Path $Store 'topics.yaml'
$Approved = Join-Path (Join-Path $StateRoot 'what-changed') "$Key.topics.yaml"
function Get-Sha([string]$Path) {
  try { (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower() }
  catch { Stop-Run "cannot read $Path ($($_.Exception.Message))" 7 }
}
function Get-Short([string]$Hash) { if ($Hash.Length -ge 12) { $Hash.Substring(0, 12) } else { $Hash } }
function Read-TopicsHash {
  if (-not (Test-Path -LiteralPath $Topics -PathType Leaf)) { Stop-Run "there is no topics.yaml file in $Store; add a topic first" 2 }
  $script:TopicsHash = Get-Sha $Topics
}
function Approve-Topics {  # copy topics.yaml as the approved version, if it still is the one with hash $TopicsHash
  $New = "$Approved.new"
  try { Copy-Item -LiteralPath $Topics -Destination $New -Force -ErrorAction Stop }
  catch { Stop-Run "could not record the approval of $Topics ($($_.Exception.Message))" 7 }
  if ((Get-Sha $New) -ne $TopicsHash) {
    Remove-Item -LiteralPath $New -Force -ErrorAction SilentlyContinue
    Stop-Run "could not record the approval of $Topics (did it change just now?)" 7
  }
  try { Move-Item -LiteralPath $New -Destination $Approved -Force -ErrorAction Stop }
  catch { Stop-Run "could not record the approval of $Topics ($($_.Exception.Message))" 7 }
  $Hosts = @(Invoke-Py @((Join-Path $Scripts 'hosts.py'), '--store', $Store, '--topics', $Approved, '--comma'))
  Write-Host "approved topics.yaml $(Get-Short $TopicsHash); scheduled runs fetch only from: $($Hosts -join ' ')"
}
function Stop-ForTopics([string]$Why) {  # show what changed against the approved copy, then stop with the approving command
  $Changes = @(Invoke-Py @((Join-Path $Scripts 'hosts.py'), '--store', $Store, '--compare', $Approved))
  $Summary = if ($Changes.Count -gt 0) { $Changes[0] } else { 'could not compare' }
  $Command = "& '$($PSCommandPath.Replace("'", "''"))' -Project '$($RealProject.Replace("'", "''"))' -ApproveTopics $(Get-Short $TopicsHash)"
  Stop-Run "topics.yaml needs your approval: $Why ($Summary). Review $Topics (the added and removed sources are listed above), then approve this version in PowerShell with: $Command" 7
}
# Approving is a step of its own, which works on a day that already ran: it records the version you
# reviewed (named by the start of its hash, so a later edit is not approved with it) and exits.
if ($ApproveTopics) {
  Read-TopicsHash
  if ($ApproveTopics -ne (Get-Short $TopicsHash)) {
    Stop-ForTopics "it is not the version you approved (its hash starts with $(Get-Short $TopicsHash), not $ApproveTopics)"
  }
  Approve-Topics
  exit 0
}

# One run at a time: a second start while a run is still going exits here,
# and one that waited for it sees its record below. Windows releases the open lock file
# when this process ends, however it ends.
$LockPath = Join-Path (Join-Path $StateRoot 'what-changed') "$Key.lock"
try { $Lock = [IO.File]::Open($LockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
catch {
  $Cause = $_.Exception
  if ($Cause.InnerException) { $Cause = $Cause.InnerException }
  if (($Cause.HResult -band 0xFFFF) -eq 32) { Write-Host 'another run is in progress'; exit 0 }  # ERROR_SHARING_VIOLATION
  Stop-Run "cannot open the lock file $LockPath ($($Cause.Message))" 2
}
if ((Test-Path -LiteralPath $Done) -and ("$(Get-Content -LiteralPath $Done -Raw)".Trim() -eq $Today)) {
  Write-Host "already ran today ($Today)"; exit 0
}

# Check the agent CLI every day, so a missing or old claude does not hide behind quiet days.
if (-not $Claude) {
  $Local = Join-Path $HOME '.local\bin\claude.exe'
  $Claude = if (Test-Path -LiteralPath $Local) { $Local } else { (Get-Command claude -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
}
if (-not $Claude -or -not (Test-Path -LiteralPath $Claude)) {
  Stop-Run "claude not found. Set -Claude to its full path (run: (Get-Command claude).Source)." 3
}
# With a time limit (the same script run-daily.sh uses): a CLI stuck mid-update would hang the job.
$Timeout = if ($env:WHAT_CHANGED_VERSION_TIMEOUT) { $env:WHAT_CHANGED_VERSION_TIMEOUT } else { '30' }
# Collect the output first: $LASTEXITCODE must be read before anything else runs.
$VersionOut = @(Invoke-Py @((Join-Path $Skill 'scripts\cli_version.py'), $Claude, "$ClaudeMin", '--timeout', $Timeout))
$VersionCode = $LASTEXITCODE
$VersionLine = if ($VersionOut.Count -gt 0) { $VersionOut[0] } else { 'cli_version.py printed nothing' }
if ($VersionCode -eq 4) { Stop-Run "$VersionLine; try again later, or raise WHAT_CHANGED_VERSION_TIMEOUT" 3 }
if ($VersionCode -ne 0) { Stop-Run "$VersionLine; unattended runs use --restricted. Update Claude Code, or set -Claude to another claude" 3 }

# A new store (no ledger, no runs.log) is approved as it is; anything else needs your approval first.
Read-TopicsHash
if (-not (Test-Path -LiteralPath $Approved -PathType Leaf)) {
  $Ledgers = @(Get-ChildItem -LiteralPath (Join-Path $Store 'ledger') -Force -ErrorAction SilentlyContinue)
  if (-not (Test-Path -LiteralPath (Join-Path $Store 'runs.log')) -and $Ledgers.Count -eq 0) {
    Write-Host -NoNewline 'first run of this store: '
    Approve-Topics
  } else {
    Stop-ForTopics 'there is no approved copy of it yet (a moved project, a new machine or a cleaned state folder)'
  }
} elseif ((Get-Sha $Approved) -ne $TopicsHash) {
  Stop-ForTopics 'it changed since you approved it'
}

# Quiet-day shortcut: exit 0 = nothing due or changed (digest written, no model, 0 tokens);
# 11 = no source could be fetched (not counted as done); 10 = an agent is needed.
# The scripts stop fetching after their 600 s budgets; run_limited.py stops them after $Limit
# seconds as the backstop for anything that misses (exit code 124).
$Limit = '900'
$Limited = Join-Path $Scripts 'run_limited.py'
$PrecheckOut = Join-Path $LogDir "$Today-precheck.out"
Invoke-Py @($Limited, $Limit, (Join-Path $Scripts 'precheck.py'), '--store', $Store, '--topics', $Approved) | Tee-Object -FilePath $PrecheckOut
$Pre = $LASTEXITCODE
if ($Pre -eq 0) { Set-Content -LiteralPath $Done -Value $Today -Encoding utf8; exit 0 }
if ($Pre -eq 124) { Stop-Run "precheck did not finish within $Limit s and was stopped; today is not counted as done" 12 }
if ($Pre -eq 11) { Stop-Run "no source of a due topic could be fetched (see $PrecheckOut); today is not counted as done" 11 }

$NowOut = @(Invoke-Py @((Join-Path $Scripts 'log_run.py'), '--now'))
$NowCode = $LASTEXITCODE
$Started = if ($NowOut.Count -gt 0) { $NowOut[0] } else { '' }
if ($NowCode -ne 0 -or $Started -notmatch 'T(\d\d:\d\d)') { Stop-Run 'log_run.py --now failed' 2 }
$RunHHMM = $Matches[1]
$StartedAt = Get-Date

# Permission rules use POSIX-style paths on Windows: C:\path\to becomes /c/path/to, and a
# leading // anchors the rule at the filesystem root. Network (UNC) paths are not supported.
function ConvertTo-RulePath([string]$Path) {
  if ($Path -notmatch '^[A-Za-z]:\\') { Stop-Run "the store and the skill must be on a drive letter, not $Path" 2 }
  '/' + $Path.Substring(0, 1).ToLower() + $Path.Substring(2).Replace('\', '/')
}
$RealStore = (Resolve-Path -LiteralPath $Store).Path
$StoreRule = ConvertTo-RulePath $RealStore
$SkillRule = ConvertTo-RulePath $Skill
if ("$StoreRule$SkillRule" -match '[\s,()]') { Stop-Run "permission rules cannot hold a path with spaces, commas or parentheses: $RealStore, $Skill" 2 }

# One token (--allow=...), so an empty value survives PowerShell 5.1, which drops empty arguments.
$Allow = @(Invoke-Py @((Join-Path $Scripts 'hosts.py'), '--store', $RealStore, '--topics', $Approved, "--allow=$FetchDomains"))
if ($LASTEXITCODE -ne 0) { Stop-Run 'hosts.py could not build the fetch allowlist' 2 }
$AllowedHosts = if ($Allow.Count -ge 1) { $Allow[0] } else { '' }
$Fetch = if ($Allow.Count -ge 2) { $Allow[1] } else { '' }
$Tools = "Read(/$SkillRule/**),Read(/$StoreRule/**),WebSearch"
if ($Fetch) { $Tools += ",$Fetch" }
$Tools += ",Edit(/$StoreRule/ledger/**),Edit(/$StoreRule/digests/**)"

# Fingerprints from the same script precheck uses, so tomorrow's precheck compares like with like.
$env:WHAT_CHANGED_ALLOWED_HOSTS = $AllowedHosts
$Urls = @(Invoke-Py @((Join-Path $Scripts 'precheck.py'), '--store', $RealStore, '--topics', $Approved, '--list-sources'))
if ($LASTEXITCODE -ne 0) { Stop-Run 'precheck.py --list-sources could not read topics.yaml' 2 }
$Prints = @()
if ($Urls.Count -gt 0) {
  $FingerprintOut = @(Invoke-Py (@($Limited, $Limit, (Join-Path $Scripts 'fingerprint.py')) + $Urls))
  if ($LASTEXITCODE -eq 124) { Stop-Run "fingerprint.py did not finish within $Limit s and was stopped" 12 }
  foreach ($Line in $FingerprintOut) {
    try { $F = $Line | ConvertFrom-Json } catch { continue }
    if ($F.ok) { $Prints += "$($F.url) -> $($F.fingerprint)" } else { $Prints += "$($F.url) -> could not fetch: $($F.detail)" }
  }
}

$Prompt = "Use the what-changed skill: run all due topics in light mode. Store: $RealStore. The skill's instructions: $Skill\SKILL.md. " +
  "Unattended run on Windows: precheck.py already ran and found work. You have no shell: do not try to run the skill's scripts. " +
  "Fingerprints computed by fingerprint.py just now (write these exact values in each ledger's Source state; do not compute your own): " +
  ($Prints -join ' ; ') + ". " +
  "The scheduler writes runs.log and runs check_ledger.py and verify_quotes.py after you finish, so do not edit runs.log. " +
  "Use $RunHHMM as the digest's Run HH:MM. " +
  "Pages can be fetched only from: $(if ($AllowedHosts) { $AllowedHosts } else { 'no hosts' }); list other sources under Could not check."

$Out = Join-Path $LogDir "$Today-claude.out"
$Err = Join-Path $LogDir "$Today-claude.err"
$env:WHAT_CHANGED_STORE = $RealStore
Push-Location -LiteralPath $RealStore
try {
  & $Claude -p $Prompt --restricted --tools 'Read,Edit,Write,WebFetch,WebSearch' --add-dir $Skill --strict-mcp-config `
    --permission-mode dontAsk --permission-prompts none --allowedTools $Tools --output-format json > $Out 2> $Err
  $AgentExit = $LASTEXITCODE
} finally { Pop-Location }
if ($AgentExit -ne 0) { Stop-Run "claude exited with code $AgentExit; see $Err" 4 }
# A run must not change the watchlist: the next runs would fetch whatever it added.
$After = 'unreadable'
try { $After = (Get-FileHash -LiteralPath $Topics -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower() } catch { }
if ($After -ne $TopicsHash) {
  $TopicsHash = $After
  Stop-ForTopics "the agent changed it during today's run, which is not counted as done"
}

# The run happened only if the agent wrote today's digest.
$Digest = Join-Path (Join-Path $RealStore 'digests') "$Today.md"
if (-not (Test-Path -LiteralPath $Digest) -or (Get-Item -LiteralPath $Digest).LastWriteTime -lt $StartedAt) {
  Stop-Run "the agent finished without writing today's digest; see $Out" 5
}
$CheckOut = Join-Path $LogDir "$Today-check_ledger.out"
Invoke-Py @((Join-Path $Scripts 'check_ledger.py'), $RealStore) | Set-Content -LiteralPath $CheckOut -Encoding utf8
if ($LASTEXITCODE -ne 0) { Stop-Run "check_ledger.py found problems in the ledgers; see $CheckOut" 6 }
Invoke-Py @($Limited, $Limit, (Join-Path $Scripts 'verify_quotes.py'), $RealStore) | Set-Content -LiteralPath (Join-Path $LogDir "$Today-verify_quotes.out") -Encoding utf8
$Quotes = $LASTEXITCODE   # unreachable pages are common, and 124 is a stopped run; recorded, not fatal

# The runs.log line comes from the clock, not from the agent.
Invoke-Py @((Join-Path $Scripts 'log_run.py'), '--store', $RealStore, '--started', $Started,
  'scope=all', 'mode=light', 'host=claude', 'logged_by=scheduler', "verify_quotes_exit=$Quotes") | Out-Null
if ($LASTEXITCODE -ne 0) { Stop-Run 'log_run.py could not write runs.log' 5 }
Set-Content -LiteralPath $Done -Value $Today -Encoding utf8
Write-Host "done; output in $LogDir"
