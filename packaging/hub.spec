# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
ICON = "../src/hub/resources/" + ("hub.icns" if IS_MAC else "hub.ico")

# Collect source and assets from THIS checkout, even if another editable hub
# installation is present in the build interpreter.
sys.path.insert(0, str(Path(SPECPATH).parent / "src"))
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = (collect_data_files("hub", includes=["resources/*", "setup_wizard/static/*",
                                             "setup_wizard/static/icons/*"])
         + copy_metadata("marketing-data-hub") + copy_metadata("fastmcp") + copy_metadata("mcp"))
hidden = (collect_submodules("hub")
          + collect_submodules("fastmcp") + collect_submodules("mcp")
          + collect_submodules("googleapiclient") + collect_submodules("google.analytics")
          + ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
             "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "duckdb"])

a = Analysis(["hub_entry.py"], pathex=["../src"], datas=datas, hiddenimports=hidden,
             noarchive=False)
pyz = PYZ(a.pure)
exe_cli = EXE(pyz, a.scripts, exclude_binaries=True, name="hub", console=True,
              icon=ICON)

g = Analysis(["hub_gui_entry.py"], pathex=["../src"], datas=datas, hiddenimports=hidden,
             noarchive=False)
pyz_g = PYZ(g.pure)
exe_gui = EXE(pyz_g, g.scripts, exclude_binaries=True, name="MarketingDataHub",
              console=False, icon=ICON)

if IS_MAC:
    # GUI first: the first executable becomes the .app's double-click target.
    # hub (the CLI) rides along in Contents/MacOS for Claude's MCP entry and
    # the daily launchd job.
    coll = COLLECT(exe_gui, g.binaries, g.datas, exe_cli, a.binaries, a.datas,
                   strip=False, upx=False, name="MarketingDataHub")
    app = BUNDLE(coll, name="Marketing Data Hub.app", icon=ICON,
                 bundle_identifier="com.marketingdatahub.app",
                 info_plist={
                     "CFBundleName": "Marketing Data Hub",
                     "CFBundleDisplayName": "Marketing Data Hub",
                     "CFBundleShortVersionString": os.environ.get("HUB_VERSION", "0.0.0"),
                     "CFBundleVersion": os.environ.get("HUB_VERSION", "0.0.0"),
                     "LSMinimumSystemVersion": "11.0",
                     "NSHighResolutionCapable": True,
                 })
else:
    coll = COLLECT(exe_cli, a.binaries, a.datas, exe_gui, g.binaries, g.datas,
                   strip=False, upx=False, name="MarketingDataHub")
