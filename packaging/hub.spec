# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = (collect_data_files("hub", includes=["resources/*", "setup_wizard/static/*"])
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
              icon="../src/hub/resources/hub.ico")

g = Analysis(["hub_gui_entry.py"], pathex=["../src"], datas=datas, hiddenimports=hidden,
             noarchive=False)
pyz_g = PYZ(g.pure)
exe_gui = EXE(pyz_g, g.scripts, exclude_binaries=True, name="MarketingDataHub",
              console=False, icon="../src/hub/resources/hub.ico")

coll = COLLECT(exe_cli, a.binaries, a.datas, exe_gui, g.binaries, g.datas,
               strip=False, upx=False, name="MarketingDataHub")
