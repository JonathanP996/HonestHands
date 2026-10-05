#!/bin/bash
# Builds "AI Integrity Guard.app" and a .dmg. Run this on a Mac.
set -e
cd "$(dirname "$0")"
APP="HonestHands"

echo "==> Checking for Python 3"
command -v python3 >/dev/null || { echo "Install Python 3 first (python.org or: xcode-select --install)"; exit 1; }

echo "==> Setting up a build environment"
python3 -m venv .buildenv
source .buildenv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> Making the app icon"
mkdir -p icon.iconset
if command -v rsvg-convert >/dev/null; then CONV="rsvg-convert -w %s -h %s icon.svg -o %s";
elif command -v sips >/dev/null && command -v qlmanage >/dev/null; then CONV="";
fi
# Use sips to rasterize the SVG via a PNG fallback if needed.
python3 - <<'PY'
import subprocess, os
sizes=[16,32,64,128,256,512,1024]
# Render SVG to a 1024 PNG using macOS's built-in tools (via a WebKit snapshot through qlmanage is unreliable;
# instead draw with CoreGraphics through a tiny Swift-free path: use 'sips' can't read svg, so use 'resvg' if present).
base=None
for tool in (["rsvg-convert","-w","1024","-h","1024","icon.svg","-o","icon.iconset/base.png"],):
    try:
        subprocess.run(tool,check=True); base="icon.iconset/base.png"; break
    except Exception: pass
if not base:
    # Fallback: let macOS render the SVG by printing it to PDF then to PNG.
    subprocess.run(["cupsfilter","icon.svg"],stdout=open("icon.iconset/base.pdf","wb")) if False else None
    try:
        subprocess.run(["qlmanage","-t","-s","1024","-o","icon.iconset","icon.svg"],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for f in os.listdir("icon.iconset"):
            if f.endswith(".png"): os.rename("icon.iconset/"+f,"icon.iconset/base.png"); base="icon.iconset/base.png"; break
    except Exception: pass
if base:
    for s in sizes:
        subprocess.run(["sips","-z",str(s),str(s),base,"--out",f"icon.iconset/icon_{s}x{s}.png"],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(["sips","-z",str(s*2),str(s*2),base,"--out",f"icon.iconset/icon_{s}x{s}@2x.png"],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
PY
if [ -f icon.iconset/base.png ]; then iconutil -c icns icon.iconset -o icon.icns 2>/dev/null || true; fi
ICONFLAG=""; [ -f icon.icns ] && ICONFLAG="--icon icon.icns"

echo "==> Building the native overlay (Swift)"
mkdir -p overlay/bin
if command -v swift >/dev/null && (cd overlay/mac && swift build -c release --quiet); then
  cp overlay/mac/.build/release/HHOverlay overlay/bin/HHOverlay
else
  echo "   (Swift not available; the app will use its built-in fallback panel)"
fi

echo "==> Building the app with PyInstaller"
rm -rf build dist
pyinstaller --noconfirm --windowed --name "$APP" $ICONFLAG \
  --add-data "ui:ui" \
  --add-data "extension:extension" \
  --add-data "overlay/bin:overlay/bin" \
  --osx-bundle-identifier "com.honesthands.app" \
  --collect-all llama_cpp \
  --hidden-import rules --hidden-import store --hidden-import engine --hidden-import ai_guard \
  --hidden-import distill --hidden-import docs --hidden-import watcher --hidden-import bridge --hidden-import overlay_client \
  main.py

# Mark it as an agent app (no Dock icon; lives in the menu bar) and name it for permission prompts.
PLIST="dist/$APP.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Needed to check your AI messages against your class rules.'" "$PLIST" 2>/dev/null || true

# Editing Info.plist above invalidates PyInstaller's signature, and Apple-silicon Macs then call a downloaded copy "damaged".
# Sign the finished bundle again (ad-hoc; no developer account needed) so it is internally consistent.
echo "==> Signing the app (ad-hoc)"
codesign --force --deep --sign - "dist/$APP.app"
codesign --verify --deep --strict "dist/$APP.app"

echo "==> Making the DMG"
rm -f "$APP.dmg"
STAGE="dmg_stage"; rm -rf "$STAGE"; mkdir "$STAGE"
cp -R "dist/$APP.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$APP" -srcfolder "$STAGE" -ov -format UDZO "$APP.dmg" >/dev/null
rm -rf "$STAGE"

echo ""
echo "==> Done:  $(pwd)/$APP.dmg"
echo "Open it, drag the app to Applications, and launch it."
echo "The first launch: right-click the app > Open (it isn't notarized by Apple), then grant Accessibility when asked."
