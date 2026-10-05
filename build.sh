#!/bin/bash
# Builds "AI Integrity Guard.app" and a .dmg. Run this on a Mac.
set -e
cd "$(dirname "$0")"
APP="HonestHands"

echo "==> Checking for Python 3"
command -v python3 >/dev/null || { echo "Install Python 3 first (python.org or: xcode-select --install)"; exit 1; }

echo "==> Numbering this build"
python3 - <<'PY'
import re, json, os
s = open("version.py").read()
n = int(re.search(r"BUILD = (\d+)", s).group(1)) + 1
open("version.py", "w").write(re.sub(r"BUILD = \d+", f"BUILD = {n}", s))
ver = re.search(r"VERSION = '([^']*)'", s).group(1)
site = os.path.join("..", "honesthands-site")
if os.path.isdir(site):      # the website tells installed copies what the newest build is
    json.dump({"build": n, "version": ver, "notes": os.environ.get("UPDATE_NOTES", ""), "url": "https://honesthands-site.vercel.app/HonestHands.dmg"},
              open(os.path.join(site, "version.json"), "w"), indent=2)
print("   build", n)
PY

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
  --hidden-import net --hidden-import updates --hidden-import version --hidden-import rules --hidden-import store --hidden-import engine --hidden-import ai_guard \
  --hidden-import distill --hidden-import docs --hidden-import watcher --hidden-import bridge --hidden-import overlay_client \
  main.py

# Mark it as an agent app (no Dock icon; lives in the menu bar) and name it for permission prompts.
PLIST="dist/$APP.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Needed to check your AI messages against your class rules.'" "$PLIST" 2>/dev/null || true

# Automatic updates: embed Sparkle and tell the app where to look (the website's appcast.xml) and which key signs updates.
if [ ! -d vendor/Sparkle.framework ]; then
  echo "==> Fetching Sparkle"
  mkdir -p vendor/dl && TAG=$(curl -s https://api.github.com/repos/sparkle-project/Sparkle/releases/latest | python3 -c "import sys,json;print(json.load(sys.stdin)['tag_name'])")
  curl -sL -o vendor/dl/s.tar.xz "https://github.com/sparkle-project/Sparkle/releases/download/$TAG/Sparkle-$TAG.tar.xz" && tar -xf vendor/dl/s.tar.xz -C vendor/dl
  cp -R vendor/dl/Sparkle.framework vendor/ && mkdir -p vendor/sparkle-bin && cp vendor/dl/bin/generate_keys vendor/dl/bin/sign_update vendor/sparkle-bin/
fi
mkdir -p "dist/$APP.app/Contents/Frameworks"
rm -rf "dist/$APP.app/Contents/Frameworks/Sparkle.framework"
cp -R vendor/Sparkle.framework "dist/$APP.app/Contents/Frameworks/"
PL="dist/$APP.app/Contents/Info.plist"
SETKV() { /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PL" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PL"; }
SETKV SUFeedURL string "https://honesthands-site.vercel.app/appcast.xml"
SETKV SUPublicEDKey string "$(cat sparkle_public_key.txt)"
SETKV SUEnableAutomaticChecks bool true
SETKV SUScheduledCheckInterval integer 14400
BUILDNO_PL=$(python3 -c "import re;print(re.search(r'BUILD = (\d+)', open('version.py').read()).group(1))")
VERSION_PL=$(python3 -c "import re;print(re.search(r\"VERSION = '([^']*)'\", open('version.py').read()).group(1))")
SETKV CFBundleVersion string "$BUILDNO_PL"
SETKV CFBundleShortVersionString string "$VERSION_PL"

# Safari's extension has to live inside a signed app. Build it with Apple's converter + Xcode and put it inside HonestHands.app, so
# Safari users only switch it on (no Xcode, no "Allow Unsigned Extensions").
SAFARI_APPEX=""
if command -v xcodebuild >/dev/null && xcrun --find safari-web-extension-converter >/dev/null 2>&1; then
  echo "==> Building the Safari extension"
  SW="$(pwd)/build/safari"; rm -rf "$SW"; mkdir -p "$SW"
  python3 - "$SW" <<'PY'
import json, shutil, sys
sys.path.insert(0, ".")
import extensions
sw = sys.argv[1]
shutil.copytree("extension", sw + "/web")
m = json.load(open("extension/manifest.json"))
open(sw + "/web/manifest.json", "w").write(json.dumps(extensions.mv2_manifest(m), indent=2))
PY
  xcrun safari-web-extension-converter "$SW/web" --project-location "$SW/proj" --app-name HonestHands --bundle-identifier com.honesthands.app \
    --macos-only --no-open --no-prompt --force >/dev/null 2>&1
  XPROJ=$(ls -d "$SW"/proj/*/HonestHands.xcodeproj | head -1)
  sed -i '' 's/PRODUCT_BUNDLE_IDENTIFIER = com.honesthands.HonestHands;/PRODUCT_BUNDLE_IDENTIFIER = com.honesthands.app;/' "$XPROJ/project.pbxproj"
  xcodebuild -project "$XPROJ" -scheme HonestHands -configuration Release -derivedDataPath "$SW/out" CODE_SIGNING_ALLOWED=NO ARCHS=arm64 ONLY_ACTIVE_ARCH=NO build >"$SW/xcode.log" 2>&1 || true
  SAFARI_APPEX="$SW/out/Build/Products/Release/HonestHands Extension.appex"
  # xcodebuild registered its scratch build with Launch Services: take that back so Safari only sees the real one
  /System/Library/Frameworks/CoreServices.framework/Versions/Current/Frameworks/LaunchServices.framework/Versions/Current/Support/lsregister -u "$SW/out/Build/Products/Release/HonestHands.app" >/dev/null 2>&1 || true
  if [ -d "$SAFARI_APPEX" ]; then
    mkdir -p "dist/$APP.app/Contents/PlugIns"
    cp -R "$SAFARI_APPEX" "dist/$APP.app/Contents/PlugIns/"
    BUILDNO=$(python3 -c "import re;print(re.search(r'BUILD = (\d+)', open('version.py').read()).group(1))")
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILDNO" "dist/$APP.app/Contents/PlugIns/HonestHands Extension.appex/Contents/Info.plist" 2>/dev/null || true
  else
    echo "   (the Safari extension did not build; see $SW/xcode.log. Continuing without it.)"
  fi
else
  echo "==> Xcode not found: skipping the built-in Safari extension"
fi

# Sign: with the Developer ID certificate if this Mac has one (then Apple can notarize it and macOS opens it without warnings),
# otherwise ad-hoc. Editing Info.plist above invalidated the first signature, so every file is signed again, inside-out.
IDENT=$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)
APPDIR="dist/$APP.app"
if [ -n "$IDENT" ]; then
  echo "==> Signing with: $IDENT"
  find "$APPDIR" -type f -not -path "*/PlugIns/*" \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \) | while read -r f; do
    file -b "$f" | grep -q "Mach-O" && codesign --force --options runtime --timestamp --entitlements entitlements.plist --sign "$IDENT" "$f"
  done
  SPK="$APPDIR/Contents/Frameworks/Sparkle.framework/Versions/B"       # Sparkle's own helpers, innermost first
  for X in "$SPK"/XPCServices/*.xpc "$SPK/Updater.app"; do [ -d "$X" ] && codesign --force --options runtime --timestamp --sign "$IDENT" "$X"; done
  codesign --force --options runtime --timestamp --sign "$IDENT" "$SPK/Autoupdate"
  codesign --force --options runtime --timestamp --sign "$IDENT" "$APPDIR/Contents/Frameworks/Sparkle.framework"
  for X in "$APPDIR"/Contents/PlugIns/*.appex; do      # the Safari extension is sandboxed: its own entitlements, signed before the app
    [ -d "$X" ] && codesign --force --options runtime --timestamp --entitlements safari.entitlements --sign "$IDENT" "$X"
  done
  codesign --force --options runtime --timestamp --entitlements entitlements.plist --sign "$IDENT" "$APPDIR"
else
  echo "==> No Developer ID certificate here: signing ad-hoc (people will see an 'unverified developer' warning)"
  for X in "$APPDIR"/Contents/PlugIns/*.appex; do [ -d "$X" ] && codesign --force --entitlements safari.entitlements --sign - "$X"; done
  codesign --force --deep --sign - "$APPDIR"
fi
codesign --verify --deep --strict "$APPDIR"

notarize() {   # notarize <file>: waits for Apple's answer (retrying if the connection hiccups); stops the build if rejected
  P="${NOTARY_PROFILE:-HonestHands}"
  NID=""
  for t in 1 2 3 4 5; do
    NID=$(xcrun notarytool submit "$1" --keychain-profile "$P" --no-wait --output-format json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null)
    [ -n "$NID" ] && break; sleep 10
  done
  [ -n "$NID" ] || { echo "Could not send the file to Apple."; exit 1; }
  echo "   submitted $NID"
  for i in $(seq 1 90); do
    ST=$(xcrun notarytool info "$NID" --keychain-profile "$P" --output-format json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
    case "$ST" in
      Accepted) echo "   status: Accepted"; return 0;;
      Invalid|Rejected) echo "Notarization was not accepted ($ST). Details: xcrun notarytool log $NID --keychain-profile $P"; exit 1;;
    esac
    sleep 15
  done
  echo "Notarization took too long. Check: xcrun notarytool info $NID --keychain-profile $P"; exit 1
}
CAN_NOTARIZE=0
if [ -n "$IDENT" ] && xcrun notarytool history --keychain-profile "${NOTARY_PROFILE:-HonestHands}" >/dev/null 2>&1; then CAN_NOTARIZE=1; fi
if [ "$CAN_NOTARIZE" = 1 ]; then
  echo "==> Notarizing the app with Apple (a few minutes)"
  ditto -c -k --keepParent "$APPDIR" "dist/$APP.zip"
  notarize "dist/$APP.zip"
  xcrun stapler staple "$APPDIR"
elif [ -n "$IDENT" ]; then
  echo "   (signed but NOT notarized: save credentials with 'xcrun notarytool store-credentials HonestHands ...')"
fi

echo "==> Making the DMG"
rm -f "$APP.dmg"
STAGE="dmg_stage"; rm -rf "$STAGE"; mkdir "$STAGE"
cp -R "dist/$APP.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$APP" -srcfolder "$STAGE" -ov -format UDZO "$APP.dmg" >/dev/null
rm -rf "$STAGE"
if [ -n "$IDENT" ]; then
  codesign --force --timestamp --sign "$IDENT" "$APP.dmg"
  if [ "$CAN_NOTARIZE" = 1 ]; then
    echo "==> Notarizing the installer"
    notarize "$APP.dmg"
    xcrun stapler staple "$APP.dmg"
  fi
fi

python3 - <<'PY'
# The appcast is what installed copies read to find the newest build; its signature must match the final .dmg byte for byte.
import re, os, subprocess, email.utils, time
s = open("version.py").read()
build = re.search(r"BUILD = (\d+)", s).group(1); ver = re.search(r"VERSION = '([^']*)'", s).group(1)
site = os.path.join("..", "honesthands-site")
if os.path.isdir(site) and os.path.exists("vendor/sparkle-bin/sign_update"):
    out = subprocess.run(["vendor/sparkle-bin/sign_update", "HonestHands.dmg"], capture_output=True, text=True).stdout.strip()
    notes = os.environ.get("UPDATE_NOTES", "") or "Improvements and fixes."
    open(os.path.join(site, "appcast.xml"), "w").write(f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>HonestHands</title>
    <item>
      <title>Version {ver} (build {build})</title>
      <pubDate>{email.utils.formatdate(time.time())}</pubDate>
      <sparkle:version>{build}</sparkle:version>
      <sparkle:shortVersionString>{ver}</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>11.0</sparkle:minimumSystemVersion>
      <description><![CDATA[{notes}]]></description>
      <enclosure url="https://honesthands-site.vercel.app/HonestHands.dmg" type="application/octet-stream" {out}/>
    </item>
  </channel>
</rss>
""")
    print("   appcast for build", build)
PY
echo ""
echo "==> Done:  $(pwd)/$APP.dmg"
echo "Open it, drag the app to Applications, and launch it."
echo "The first launch: right-click the app > Open (it isn't notarized by Apple), then grant Accessibility when asked."
