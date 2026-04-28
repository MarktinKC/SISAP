$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimePython = "C:\Users\rock_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path $runtimePython) {
  & $runtimePython (Join-Path $root "server.py")
}
else {
  python (Join-Path $root "server.py")
}
