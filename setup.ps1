param([ValidateSet("preflight","venv","online")][string]$Mode="preflight")
$ErrorActionPreference="Stop"
$Py=if($env:PYTHON){$env:PYTHON}else{"python"}
switch($Mode){
 "preflight" { & $Py -X utf8 tools\local_runtime_preflight.py --root . --json; exit $LASTEXITCODE }
 "venv" { & $Py -m venv .venv; if($LASTEXITCODE-ne 0){exit $LASTEXITCODE}; Write-Host "venv created; no network install performed" }
 "online" {
   if(-not(Test-Path .venv)){& $Py -m venv .venv; if($LASTEXITCODE-ne 0){exit $LASTEXITCODE}}
   $Vpy=Join-Path ".venv" "Scripts\python.exe"
   & $Vpy -m pip install --upgrade pip; if($LASTEXITCODE-ne 0){exit $LASTEXITCODE}
   & $Vpy -m pip install -e .; exit $LASTEXITCODE
 }
}
