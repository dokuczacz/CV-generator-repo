# Run chunker for omniflowbeta repo
# Edit $RepoRoot if your repo lives elsewhere
$RepoRoot = "C:\\AI memory\\omniflowbeta"
$Out = "C:\\Users\\Mariusz\\OneDrive\\Pulpit\\Architecture-Analysis\\cv-generator-handoff\\omniflowbeta"
python .\scripts\chunk_repo.py --root $RepoRoot --output $Out --chunk-bytes 8388608 --with-index
Write-Host "Completed chunking $RepoRoot -> $Out"