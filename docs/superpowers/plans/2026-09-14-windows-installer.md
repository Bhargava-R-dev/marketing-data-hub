# Windows Installer + Release Pipeline Implementation Plan (Sub-project 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A non-technical Windows user downloads one `.exe` from growthbybhargava.com, runs it, and lands in the setup page — Python included, icon on the desktop, nothing else to do. Every tagged release builds the wheel (PyPI) and the installer (GitHub Release) automatically.

**Architecture:** PyInstaller builds a one-folder bundle with two executables sharing one runtime: `hub.exe` (console, the full CLI — also what Claude and the scheduler call) and `MarketingDataHub.exe` (windowed, opens the home page without a console). Inno Setup wraps that folder into a per-user installer (no admin) with Start Menu / Desktop icons. A GitHub Actions workflow on `v*` tags publishes the wheel via PyPI trusted publishing and attaches `MarketingDataHub-Setup.exe` (stable name) to the release, which the website's download button links to.

**Tech Stack:** PyInstaller 6 (onedir), Inno Setup 6 (`iscc`), GitHub Actions (`windows-latest` + `ubuntu-latest`), `pypa/gh-action-pypi-publish`.

**Repo:** `C:\Users\Laptop-577\Documents\data collection`, branch `master`. Tests: `python -m pytest -q` (322 passing).

---

## File structure

Create:
- `packaging/hub_entry.py` — console entry → `hub.cli:app`.
- `packaging/hub_gui_entry.py` — windowed entry → `hub setup`.
- `packaging/hub.spec` — PyInstaller spec (two EXEs, one COLLECT, data + metadata).
- `packaging/installer.iss` — Inno Setup script.
- `packaging/README.md` — how to build locally + how a release happens.
- `.github/workflows/release.yml` — tag → PyPI + GitHub Release.
- `.github/workflows/test.yml` — pytest on push/PR (cheap safety net for the release workflow).

Modify:
- `pyproject.toml` — version `0.5.0`.
- `src/hub/core/shortcut.py` — frozen launcher prefers `MarketingDataHub.exe`.
- `tests/test_shortcut.py` — covers that.
- `.gitignore` — `build/`, `packaging/dist/`.
- `docs/google-verification.md` — add a PyPI trusted-publisher section (user action).
- Website (separate repo, after the first release): `lib/hubRelease.ts` download URL.

---

### Task 1: Frozen launcher prefers the windowed exe

**Files:**
- Modify: `src/hub/core/shortcut.py:launcher_command`
- Test: `tests/test_shortcut.py`

- [ ] **Step 1: Failing test** (append)

```python
def test_launcher_frozen_prefers_gui_exe(monkeypatch, tmp_path):
    (tmp_path / "MarketingDataHub.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "hub.exe"))
    assert shortcut.launcher_command() == (str(tmp_path / "MarketingDataHub.exe"), "")
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_shortcut.py -q` → 1 failed.

- [ ] **Step 3: Implement** — replace the frozen branch of `launcher_command`:

```python
    if getattr(sys, "frozen", False):
        gui = Path(sys.executable).with_name("MarketingDataHub.exe")
        if gui.exists():
            return str(gui), ""  # windowed build: opens the home page, no console
        return sys.executable, args
```

(The GUI exe ignores `--config`: it always resolves the per-user home, which is what the installer sets up.)

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_shortcut.py -q
git add src/hub/core/shortcut.py tests/test_shortcut.py
git commit -m "feat: frozen shortcut targets the windowed MarketingDataHub.exe"
```

---

### Task 2: PyInstaller bundle

**Files:**
- Create: `packaging/hub_entry.py`, `packaging/hub_gui_entry.py`, `packaging/hub.spec`
- Modify: `pyproject.toml` (version), `.gitignore`

- [ ] **Step 1: Install the tool**

```bash
python -m pip install "pyinstaller>=6.10"
```

- [ ] **Step 2: Entry scripts**

`packaging/hub_entry.py`:
```python
from hub.cli import app

if __name__ == "__main__":
    app()
```

`packaging/hub_gui_entry.py`:
```python
import sys

from hub.cli import app

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "setup"]  # windowed: always the home page
    app()
```

- [ ] **Step 3: Spec** — `packaging/hub.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = (collect_data_files("hub", includes=["resources/*", "setup_wizard/static/*"])
         + copy_metadata("marketing-data-hub"))
hidden = (collect_submodules("hub")
          + collect_submodules("fastmcp") + collect_submodules("mcp")
          + collect_submodules("googleapiclient") + collect_submodules("google.analytics")
          + ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
             "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "duckdb"])

a = Analysis(["hub_entry.py"], pathex=["../src"], datas=datas, hiddenimports=hidden, noarchive=False)
pyz = PYZ(a.pure)
exe_cli = EXE(pyz, a.scripts, exclude_binaries=True, name="hub", console=True,
              icon="../src/hub/resources/hub.ico")

g = Analysis(["hub_gui_entry.py"], pathex=["../src"], datas=datas, hiddenimports=hidden, noarchive=False)
pyz_g = PYZ(g.pure)
exe_gui = EXE(pyz_g, g.scripts, exclude_binaries=True, name="MarketingDataHub", console=False,
              icon="../src/hub/resources/hub.ico")

coll = COLLECT(exe_cli, a.binaries, a.datas, exe_gui, g.binaries, g.datas,
               strip=False, upx=False, name="MarketingDataHub")
```

- [ ] **Step 4: Version bump + ignore build output**

`pyproject.toml`: `version = "0.5.0"`; then `python -m pip install -e . -q --no-deps` so `copy_metadata` sees 0.5.0.
`.gitignore`: add `build/` and `packaging/dist/`.

- [ ] **Step 5: Build and smoke-test**

```bash
cd packaging && pyinstaller --noconfirm --clean --distpath dist --workpath ../build hub.spec
```

Then (still in `packaging/`):
```bash
dist/MarketingDataHub/hub.exe --version
mkdir -p "$TEMP/mdh-frozen" && dist/MarketingDataHub/hub.exe setup --no-browser --port 8771 --config "$TEMP/mdh-frozen/config.yaml" &
```
Open http://127.0.0.1:8771 in the Browser pane — Welcome must render (static files bundled), `/api/state` must report `client_source: bundled`. Kill it. Also check the MCP handshake works from the frozen exe:
```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}\n' | dist/MarketingDataHub/hub.exe mcp --config "$TEMP/mdh-frozen/config.yaml" | head -c 300
```
Expected: a JSON `result` with `serverInfo`. Fix hidden imports in the spec until all three pass. Expect ~150–200 MB for the folder.

- [ ] **Step 6: Commit**

```bash
git add packaging/hub_entry.py packaging/hub_gui_entry.py packaging/hub.spec pyproject.toml .gitignore
git commit -m "build: PyInstaller bundle - hub.exe (CLI) + MarketingDataHub.exe (windowed home page)"
```

---

### Task 3: Inno Setup installer

**Files:**
- Create: `packaging/installer.iss`, `packaging/README.md`

- [ ] **Step 1: Install Inno Setup** — `winget install --id JRSoftware.InnoSetup -e --silent` (adds `ISCC.exe` under `%LOCALAPPDATA%\Programs\Inno Setup 6\` or `C:\Program Files (x86)\Inno Setup 6\`).

- [ ] **Step 2: Script** — `packaging/installer.iss`:

```ini
#define AppName "Marketing Data Hub"
#define AppVersion GetEnv("HUB_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7E1C5C1A-2B2E-4B9E-9C2A-MDH000000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Growth by Bhargava
AppPublisherURL=https://growthbybhargava.com/tools/marketing-data-hub
AppSupportURL=https://github.com/Bhargava-R-dev/marketing-data-hub/issues
DefaultDirName={localappdata}\Programs\MarketingDataHub
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MarketingDataHub-Setup
SetupIconFile=..\src\hub\resources\hub.ico
UninstallDisplayIcon={app}\MarketingDataHub.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\MarketingDataHub\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\MarketingDataHub.exe"; IconFilename: "{app}\_internal\hub\resources\hub.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\MarketingDataHub.exe"; IconFilename: "{app}\_internal\hub\resources\hub.ico"

[Run]
Filename: "{app}\MarketingDataHub.exe"; Description: "Open Marketing Data Hub now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\hub.exe"; Parameters: "schedule --remove"; Flags: runhidden; RunOnceId: "RemoveTask"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
FinishedLabel=Installed. Your data and settings live in %LOCALAPPDATA%\MarketingDataHub — they are kept if you ever uninstall.
```

(Check where PyInstaller 6 put `hub.ico` inside the bundle — `_internal\hub\resources\hub.ico` for onedir — and fix the `IconFilename` paths if different.)

- [ ] **Step 3: Build + silent install test**

```bash
cd packaging && HUB_VERSION=0.5.0 "/c/Users/Laptop-577/AppData/Local/Programs/Inno Setup 6/ISCC.exe" installer.iss
ls -la dist/MarketingDataHub-Setup.exe
dist/MarketingDataHub-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
"$LOCALAPPDATA/Programs/MarketingDataHub/hub.exe" --version
ls "$APPDATA/Microsoft/Windows/Start Menu/Programs/Marketing Data Hub.lnk" "$USERPROFILE/Desktop/Marketing Data Hub.lnk"
```
Then launch the installed `MarketingDataHub.exe` via PowerShell `Start-Process`, confirm http://127.0.0.1:8770 answers within ~10 s (it will create the real per-user home `%LOCALAPPDATA%\MarketingDataHub` on this machine — that is fine and expected; delete it afterwards if you don't want a second hub here), stop it, then uninstall silently:
```bash
"$LOCALAPPDATA/Programs/MarketingDataHub/unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES
```
and confirm the folder and shortcuts are gone. **Careful:** the uninstaller runs `hub.exe schedule --remove`, which removes the *shared* task name "MarketingDataHub Daily Sync" — re-register the real hub's task afterwards with `python -m hub.cli schedule` from the repo folder.

- [ ] **Step 4: `packaging/README.md`**

```markdown
# Building the Windows installer

Local (needs Python 3.12, `pip install pyinstaller`, Inno Setup 6):

    cd packaging
    pyinstaller --noconfirm --clean --distpath dist --workpath ../build hub.spec
    HUB_VERSION=$(python -c "import tomllib;print(tomllib.load(open('../pyproject.toml','rb'))['project']['version'])") \
      ISCC.exe installer.iss      # -> dist/MarketingDataHub-Setup.exe

Release (CI does all of this): bump `version` in pyproject.toml, commit, then

    git tag v0.5.0 && git push origin v0.5.0

`.github/workflows/release.yml` publishes the wheel to PyPI (trusted publishing)
and attaches `MarketingDataHub-Setup.exe` + a versioned copy to the GitHub
Release. The website's download button points at
`releases/latest/download/MarketingDataHub-Setup.exe`.
```

- [ ] **Step 5: Commit**

```bash
git add packaging/installer.iss packaging/README.md
git commit -m "build: Inno Setup installer (per-user, icons, uninstall removes the daily task)"
```

---

### Task 4: CI — tests on push, release on tag

**Files:**
- Create: `.github/workflows/test.yml`, `.github/workflows/release.yml`
- Modify: `docs/google-verification.md` (append PyPI section)

- [ ] **Step 1: `test.yml`**

```yaml
name: tests
on:
  push: { branches: [master] }
  pull_request:
jobs:
  pytest:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix: { os: [ubuntu-latest, windows-latest] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -q
```

- [ ] **Step 2: `release.yml`**

```yaml
name: release
on:
  push:
    tags: ["v*"]
jobs:
  wheel:
    runs-on: ubuntu-latest
    permissions: { id-token: write, contents: read }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install build && python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
  installer:
    runs-on: windows-latest
    permissions: { contents: write }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install -e . "pyinstaller>=6.10"
      - run: choco install innosetup --no-progress -y
      - name: Build bundle
        working-directory: packaging
        run: pyinstaller --noconfirm --clean --distpath dist --workpath ../build hub.spec
      - name: Build installer
        working-directory: packaging
        shell: pwsh
        run: |
          $env:HUB_VERSION = "${{ github.ref_name }}".TrimStart("v")
          & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
          Copy-Item dist\MarketingDataHub-Setup.exe "dist\MarketingDataHub-Setup-$env:HUB_VERSION.exe"
      - name: Smoke test
        run: packaging\dist\MarketingDataHub\hub.exe --version
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            packaging/dist/MarketingDataHub-Setup.exe
            packaging/dist/MarketingDataHub-Setup-*.exe
          generate_release_notes: true
```

- [ ] **Step 3: PyPI trusted publisher (user action)** — append to `docs/google-verification.md` a section "H. PyPI trusted publishing (one time)": on pypi.org → project `marketing-data-hub` → Publishing → add GitHub publisher: owner `Bhargava-R-dev`, repo `marketing-data-hub`, workflow `release.yml`, environment blank. Until this exists the `wheel` job fails (the installer job still succeeds — jobs are independent).

- [ ] **Step 4: Commit + push**

```bash
git add .github/workflows/test.yml .github/workflows/release.yml docs/google-verification.md
git commit -m "ci: pytest on push; tagged releases publish to PyPI and attach the Windows installer"
git push origin master
```

Watch the `tests` workflow go green on GitHub before tagging.

---

### Task 5: First release + website flip

- [ ] **Step 1: Tag** (ask the user first — this publishes)

```bash
git tag v0.5.0 && git push origin v0.5.0
```

Watch `release` with `gh run watch`. Fix + re-tag (`v0.5.1`) if the Windows job fails; never force-move a tag.

- [ ] **Step 2: Verify the asset**

```bash
gh release view v0.5.0 --json assets --jq '.assets[].name'
curl -sIL https://github.com/Bhargava-R-dev/marketing-data-hub/releases/latest/download/MarketingDataHub-Setup.exe | grep -i "^HTTP\|content-length"
```

- [ ] **Step 3: Website** — in `Bhargava-Website/bhargava-next/lib/hubRelease.ts` set
`HUB_WINDOWS_DOWNLOAD_URL = \`${HUB_REPO_URL}/releases/latest/download/MarketingDataHub-Setup.exe\`` and change the `v0.4` note on the tools page to `v0.5`; also update `HUB_REPO_URL` to the `Bhargava-R-dev` spelling. Branch `tools/download-link`, PR, user merges.

- [ ] **Step 4: README** — Quick start already says "download the installer"; add the direct link.

---

## Self-review

- **Spec coverage:** PyInstaller onedir `hub.exe` ✓ T2 (+ windowed launcher, needed for the no-console icon from the addendum); Inno Setup per-user install, Start Menu shortcut, uninstall removes task but keeps data ✓ T3 (the 6am task is registered by the wizard's Done step rather than the installer, since the config doesn't exist until setup runs); release workflow tag → PyPI + GitHub Release, version from pyproject ✓ T4 (`copy_metadata` makes `--version`/`/api/version` work frozen); MCP entry points at `hub.exe` ✓ (existing `mcp_command` frozen branch, verified in T2 smoke test); website download flip ✓ T5.
- **Placeholders:** none. The AppId GUID is a fixed literal chosen here; keep it forever so upgrades replace the same install.
- **Consistency:** asset name `MarketingDataHub-Setup.exe` is identical in installer.iss, release.yml, hubRelease.ts, README; bundle folder name `MarketingDataHub` matches spec COLLECT ↔ iss `Source` ↔ workflow paths.
