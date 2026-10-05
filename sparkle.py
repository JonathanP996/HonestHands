"""Automatic updates with Sparkle (the standard Mac updater). The installed app carries Sparkle.framework; it checks the
website's appcast.xml, shows Apple-style 'update available' windows, downloads, installs and relaunches by itself.
Run from source there is no framework, so none of this is active (updates.py's simple banner covers that case)."""
import sys
from pathlib import Path

_controller = None


def framework_path():
    try:
        contents = Path(sys.executable).resolve().parents[1]
        p = contents / 'Frameworks' / 'Sparkle.framework'
        return p if contents.name == 'Contents' and p.exists() else None
    except Exception:
        return None


def start():
    """Call on the main thread. True if Sparkle is running."""
    global _controller
    p = framework_path()
    if _controller is not None:
        return True
    if p is None:
        return False
    try:
        import objc
        objc.loadBundle('Sparkle', {}, bundle_path=str(p))
        cls = objc.lookUpClass('SPUStandardUpdaterController')
        _controller = cls.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(True, None, None)
        return True
    except Exception as e:
        print('[sparkle] could not start:', e, flush=True)
        _controller = None
        return False


def active():
    return _controller is not None


def check_now():
    """Settings > Check for updates: Sparkle shows its own window with the answer."""
    if _controller is not None:
        _controller.checkForUpdates_(None)
        return True
    return False
