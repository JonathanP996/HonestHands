"""Builds the HonestHands browser extension for each supported browser from the one source in extension/.

  Chrome, Edge  -> the extension as is (Manifest V3, "Load unpacked")
  Firefox       -> the same code with a Manifest V2 file (Firefox grants the permissions at install)
  Safari        -> the same code, converted by Apple's tool into a small helper app and built with Xcode
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from store import APP_DIR

FIREFOX_ID = 'honesthands@honesthands.app'


def source_dir():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return Path(base) / 'extension'


def dest_for(kind):
    # Chrome/Edge/Firefox load straight from a folder, so it goes somewhere easy to find: the Downloads folder.
    downloads = Path.home() / 'Downloads'
    return {'chromium': downloads / 'HonestHands Extension', 'firefox': downloads / 'HonestHands Extension (Firefox)',
            'safari': APP_DIR / 'extension-safari'}[kind]


def _fresh_copy(src, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def mv2_manifest(m, firefox=False):
    """Manifest V2 with a background page: the broadest-compatible form for Firefox and Safari."""
    m = json.loads(json.dumps(m))
    m['manifest_version'] = 2
    perms = list(m.pop('permissions', [])) + list(m.pop('host_permissions', []))
    m['permissions'] = perms
    m['background'] = {'scripts': ['background.js'], 'persistent': False}
    if firefox:
        m['browser_specific_settings'] = {'gecko': {'id': FIREFOX_ID, 'strict_min_version': '115.0'}}
    return m


def prepare(kind, source=None, dest=None):
    """Writes the extension for this kind of browser. Returns {'dir', 'notes'} or raises RuntimeError."""
    src = Path(source) if source else source_dir()
    if not (src / 'manifest.json').exists():
        raise RuntimeError("The extension files weren't found in this copy of the app.")
    dest = Path(dest) if dest else dest_for(kind)
    if kind == 'chromium':
        _fresh_copy(src, dest)
        return {'dir': str(dest)}
    manifest = json.loads((src / 'manifest.json').read_text())
    if kind == 'firefox':
        _fresh_copy(src, dest)
        (dest / 'manifest.json').write_text(json.dumps(mv2_manifest(manifest, firefox=True), indent=2))
        return {'dir': str(dest), 'file': str(dest / 'manifest.json')}
    if kind == 'safari':
        built_in = bundled_safari()
        if built_in:
            return {'dir': str(built_in), 'bundled': True}        # nothing to build: it ships inside the app
        return _prepare_safari(src, manifest, dest)
    raise RuntimeError('Unknown browser type.')


def bundled_safari():
    """The app that carries the ready-made Safari extension (this app, when installed), or None when run from source."""
    try:
        contents = Path(sys.executable).resolve().parents[1]
        if contents.name == 'Contents' and any((contents / 'PlugIns').glob('*.appex')):
            return contents.parent
    except Exception:
        pass
    return None


SAFARI_EXT_ID = 'com.honesthands.app.Extension'


def show_in_safari():
    """Open Safari straight to this extension's switch (Settings > Extensions). False if Safari can't do that here, so the
    caller can just open Safari instead."""
    try:
        import threading
        import SafariServices
        done, out = threading.Event(), []
        def handler(err):
            out.append(err)
            done.set()
        SafariServices.SFSafariApplication.showPreferencesForExtensionWithIdentifier_completionHandler_(SAFARI_EXT_ID, handler)
        return bool(done.wait(3) and out and out[0] is None)
    except Exception:
        return False


def _have_xcode():
    try:
        subprocess.run(['xcrun', '--find', 'safari-web-extension-converter'], check=True, capture_output=True, timeout=20)
        return True
    except Exception:
        return False


def _prepare_safari(src, manifest, dest):
    if not _have_xcode():
        raise RuntimeError('Safari support needs Xcode (free in the App Store) for now. Install it, open it once to accept its '
                           'license, then try again. A ready-made Safari version is planned.')
    work = dest.parent / '.safari-work'
    if work.exists():
        shutil.rmtree(work)
    web = work / 'web'
    shutil.copytree(src, web)
    (web / 'manifest.json').write_text(json.dumps(mv2_manifest(manifest), indent=2))
    proj_dir = work / 'proj'
    app_name = 'HonestHands Safari'
    r = subprocess.run(['xcrun', 'safari-web-extension-converter', str(web), '--project-location', str(proj_dir), '--app-name', app_name,
                        '--bundle-identifier', 'app.honesthands.safari', '--macos-only', '--no-open', '--no-prompt', '--force'],
                       capture_output=True, text=True, timeout=180)
    xproj = next(proj_dir.glob(f'*/{app_name}.xcodeproj'), None) if proj_dir.exists() else None
    if r.returncode != 0 or not xproj:
        raise RuntimeError('Apple\'s converter could not prepare the Safari extension: ' + (r.stderr or r.stdout)[-300:])
    pbx = xproj / 'project.pbxproj'
    text = pbx.read_text()
    # the converter names the app and its extension inconsistently; the extension's id must start with the app's
    text = re.sub(r'PRODUCT_BUNDLE_IDENTIFIER = "?app\.honesthands\.HonestHands-Safari"?;', 'PRODUCT_BUNDLE_IDENTIFIER = app.honesthands.safari;', text)
    pbx.write_text(text)
    build = work / 'build'
    b = subprocess.run(['xcodebuild', '-project', str(xproj), '-scheme', app_name, '-configuration', 'Debug', '-derivedDataPath', str(build),
                        'CODE_SIGN_IDENTITY=-', 'CODE_SIGNING_REQUIRED=YES', 'CODE_SIGN_STYLE=Manual', 'DEVELOPMENT_TEAM=', 'ONLY_ACTIVE_ARCH=YES', 'build'],
                       capture_output=True, text=True, timeout=600)
    built = build / 'Build' / 'Products' / 'Debug' / f'{app_name}.app'
    if b.returncode != 0 or not built.exists():
        raise RuntimeError('Xcode could not build the Safari extension: ' + (b.stdout[-400:] or b.stderr[-400:]))
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(built, dest / f'{app_name}.app')
    shutil.rmtree(work, ignore_errors=True)
    return {'dir': str(dest), 'app': str(dest / f'{app_name}.app')}
