# -*- mode: python ; coding: utf-8 -*-
# v3.7.4：打包方式从 onefile 改成 onedir。
#
# onefile 每次启动都要把整个 exe（14MB）解压到 %TEMP%\_MEIxxxx 再运行，
# 这段解压 1.2-4.2s，是「冷启动 5 秒内」唯一卡不过去的环节 —— 代码再快也没用。
# onedir 把依赖摊在目录里，启动时少了整包解压，代价是分发变成一个文件夹。
#
# 目录结构（PyInstaller 6.x）：
#   dist/无限画布/无限画布.exe
#   dist/无限画布/_internal/{canvas.html, art/, python*.dll, ...}
#
# 用户数据（.env / 日志 / WebView2 profile）不在这个目录里，见 server.py 的
# app_dir() / data_dir()。分发时整个文件夹打 zip 即可，不要塞 .env。

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('canvas.html', '.'), ('app.ico', '.'), ('mark.png', '.'),
           ('splash.dat', '.'), ('art', 'art')],
    # requests 在 server.py 里是惰性导入（模块全局名上放了个代理对象），
    # PyInstaller 的静态分析扫不到 `import requests`，不写这一行就会打出一个
    # 出图全挂的包 —— 表现是启动日志里反复刷 "missing dependency: pip install requests"，
    # 静态资源却一切正常，很容易漏。
    hiddenimports=['requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='无限画布',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 会压缩 DLL，启动时再解压回来 —— onedir 要的就是省这一步，所以关掉
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='无限画布',
)
