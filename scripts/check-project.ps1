$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ((Split-Path $Repo -Leaf) -ne "Sticker_Preprocessor") { throw "WRONG_REPOSITORY" }
Set-Location $Repo

$Runtime = Join-Path $Repo ".runtime"
$TempDir = Join-Path $Runtime "temp"
$TestTemp = Join-Path $Runtime "test-temp"
$ModelDir = Join-Path $Runtime "models\rembg"
New-Item -ItemType Directory -Force -Path $TempDir,$TestTemp,$ModelDir | Out-Null
$env:TMP = $TempDir
$env:TEMP = $TempDir
$env:TMPDIR = $TempDir
$env:U2NET_HOME = $ModelDir

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) { throw "VIRTUAL_ENV_MISSING" }
& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) and sys.version_info < (3,14) else 1)"
if ($LASTEXITCODE -ne 0) { throw "PYTHON_VERSION_INVALID" }

& $Python -m compileall src tests
if ($LASTEXITCODE -ne 0) { throw "COMPILE_FAILED" }
& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "RUFF_FAILED" }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "PYTEST_FAILED" }
& $Python -m sticker_preprocessor --self-check
if ($LASTEXITCODE -ne 0) { throw "SELF_CHECK_FAILED" }
& $Python -m sticker_preprocessor --ui-smoke-test
if ($LASTEXITCODE -ne 0) { throw "UI_SMOKE_FAILED" }

$StaticUiScan = @"
import ast
from pathlib import Path
import sys

ui_source = Path('src/sticker_preprocessor/ui/main_window.py').read_text(encoding='utf-8')
preview_source = Path('src/sticker_preprocessor/preview.py').read_text(encoding='utf-8')

title = '\u8d34\u7eb8\u900f\u660e\u80cc\u666f\u5904\u7406\u5668'
web_bg = '\u7f51\u9875\u80cc\u666f'
web_checker = '\u7f51\u9875\u68cb\u76d8'
required = [
    title,
    'reset_btn',
    'progress',
    'save_as_btn',
    'open_output_btn',
    web_bg,
]
missing = [item for item in required if item not in ui_source]
if missing:
    print('STATIC_UI_MISSING ' + ','.join(missing))
    sys.exit(1)
quote = chr(34)
if ('DEFAULT_BACKGROUND_LABEL = ' + quote + web_bg + quote) not in ui_source:
    print('STATIC_DEFAULT_PREVIEW_INVALID')
    sys.exit(1)
if web_checker in ui_source:
    print('STATIC_CHECKERBOARD_DEFAULT_FOUND')
    sys.exit(1)
if 'ImageDraw' in preview_source or 'rectangle(' in preview_source or 'tile =' in preview_source:
    print('STATIC_WEB_PREVIEW_CHECKER_PATTERN_FOUND')
    sys.exit(1)

tree = ast.parse(ui_source)
class DirectCallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.direct_calls = set()
    def visit_FunctionDef(self, node):
        return
    def visit_Lambda(self, node):
        return
    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name):
            self.direct_calls.add(func.id)
        elif isinstance(func, ast.Attribute):
            self.direct_calls.add(func.attr)
        self.generic_visit(node)

def direct_calls(function_name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'MainWindow':
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == function_name:
                    visitor = DirectCallVisitor()
                    for stmt in item.body:
                        visitor.visit(stmt)
                    return visitor.direct_calls
    return set()

if 'load_image' in direct_calls('choose_image'):
    print('STATIC_SYNC_LOAD_FOUND')
    sys.exit(1)
if {'export_png', 'export_png_to_path'} & direct_calls('export_current'):
    print('STATIC_SYNC_EXPORT_FOUND')
    sys.exit(1)
"@
& $Python -c $StaticUiScan
if ($LASTEXITCODE -ne 0) { throw "STATIC_UI_SOURCE_CHECK_FAILED" }

$TrackedFiles = @(git ls-files)
if ($TrackedFiles.Count -gt 0) {
    $Conflict = Select-String -Path $TrackedFiles -Pattern "^(<<<<<<<|=======|>>>>>>>)" -ErrorAction SilentlyContinue
    if ($Conflict) { throw "GIT_CONFLICT_MARKERS_FOUND" }

    $MojibakeScan = @"
from pathlib import Path
import subprocess
import sys

files = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
bad = tuple(chr(x) for x in (0x9225, 0x8133, 0x6D93, 0x59AB, 0x9428, 0x951B, 0x93C4, 0x6D60))
hits = []
for name in files:
    path = Path(name)
    if path.is_file():
        text = path.read_text(encoding='utf-8', errors='ignore')
        if any(marker in text for marker in bad):
            hits.append(name)
if hits:
    print(chr(10).join(hits))
sys.exit(1 if hits else 0)
"@
    & $Python -c $MojibakeScan
    if ($LASTEXITCODE -ne 0) { throw "MOJIBAKE_FOUND" }
}

$Forbidden = $TrackedFiles | Where-Object {
    $_ -match "^\.venv/" -or
    $_ -match "^\.runtime/" -or
    $_ -match "\.(log|onnx|pt|pth|tmp|temp|jpg|jpeg|webp|png|gif|db|sqlite|env|zip|7z|tar|gz)`$"
}
$Forbidden = $Forbidden | Where-Object { $_ -ne "output/.gitkeep" }
if ($Forbidden) { $Forbidden | ForEach-Object { Write-Error "FORBIDDEN_TRACKED_FILE $_" }; throw "FORBIDDEN_TRACKED_FILES" }

if ($TrackedFiles.Count -gt 0) {
    $SecretPattern = ("BEGIN " + "(RSA|OPENSSH|PRIVATE)" + " KEY|AKIA" + "[0-9A-Z]{16}|SECRET_" + "KEY|API_" + "KEY")
    $SecretLike = Select-String -Path $TrackedFiles -Pattern $SecretPattern -ErrorAction SilentlyContinue
    if ($SecretLike) { throw "SECRET_LIKE_CONTENT_FOUND" }
}

$Large = $TrackedFiles | ForEach-Object {
    $item = Get-Item $_ -ErrorAction SilentlyContinue
    if ($item -and $item.Length -gt 5MB) { $_ }
}
if ($Large) { $Large | ForEach-Object { Write-Error "TRACKED_LARGE_FILE $_" }; throw "TRACKED_LARGE_FILES" }

git diff --check
if ($LASTEXITCODE -ne 0) { throw "GIT_DIFF_CHECK_FAILED" }

Write-Host "STICKER_PREPROCESSOR_PROJECT_CHECK_PASS"
