# Building the Windows installer

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

## Releasing

CI does all of this. Bump `version` in `pyproject.toml`, commit, then:

    git tag v0.5.0 && git push origin v0.5.0

`.github/workflows/release.yml` publishes the wheel to PyPI (trusted
publishing — see docs/google-verification.md section H) and attaches
`MarketingDataHub-Setup.exe` plus a versioned copy to the GitHub Release. The
website's download button links to
`releases/latest/download/MarketingDataHub-Setup.exe`, so it always serves the
newest release without a website change.
