# Building the installers

## Windows

Local build (needs Python 3.12, `pip install pyinstaller`, and Inno Setup 6):

    cd packaging
    pyinstaller --noconfirm --clean --distpath dist --workpath ../build hub.spec
    HUB_VERSION=0.5.0 ISCC.exe installer.iss      # -> dist/MarketingDataHub-Setup.exe

The bundle folder `dist/MarketingDataHub/` contains two executables sharing one
runtime: `hub.exe` (the full CLI — what Claude's MCP entry and the daily task
call) and `MarketingDataHub.exe` (windowed; opens the home page with no console
— what the Desktop / Start Menu icons point at).

Silent install / uninstall for testing:

    dist/MarketingDataHub-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    "%LOCALAPPDATA%\Programs\MarketingDataHub\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES

## macOS

Local build (needs Python 3.12 and `pip install pyinstaller`; `hdiutil` ships
with macOS):

    cd packaging
    HUB_VERSION=0.7.1 pyinstaller --noconfirm --clean --distpath dist --workpath ../build hub.spec
    python smoke_test.py "dist/Marketing Data Hub.app"
    ./build_dmg.sh "dist/Marketing Data Hub.app" dist/MarketingDataHub.dmg

`Marketing Data Hub.app` holds two executables in `Contents/MacOS`: `hub` (the
full CLI — Claude's MCP entry and the daily launchd job call it) and
`MarketingDataHub` (windowed; opens the home page — the Dock/Launchpad icon).
Users open the `.dmg` and drag the app onto Applications. Data and settings live
in `~/.marketing-data-hub`, so they survive deleting the app. `hub schedule`
installs a launchd agent at `~/Library/LaunchAgents/com.marketingdatahub.dailysync.plist`.

The app is not yet notarized, so macOS shows an "unidentified developer"
warning on first launch: right-click the app, choose Open, then Open again (or
Privacy & Security > Open Anyway). Notarizing needs an Apple Developer ID
($99/yr) — add the signing and `notarytool` steps to the `macos` job in
`release.yml` once there is one. CI builds Apple Silicon (`arm64`) and Intel
(`x64`) images separately.

## Releasing

CI does all of this. Bump `version` in `pyproject.toml`, commit, then:

    git tag v0.5.0 && git push origin v0.5.0

`.github/workflows/release.yml` publishes the wheel to PyPI (trusted
publishing — see docs/google-verification.md section H) and attaches
`MarketingDataHub-Setup.exe`, `MarketingDataHub-macOS-arm64.dmg` and
`MarketingDataHub-macOS-x64.dmg` (each plus a versioned copy) to the GitHub Release. The
website's download button links to
`releases/latest/download/MarketingDataHub-Setup.exe`, so it always serves the
newest release without a website change.
