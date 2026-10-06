# Windows version: plan and status

Work happens on the `windows` branch. Nothing here changes the Mac app until it is merged.

## What is shared (no change needed)
The screens (`ui/`), the AI guard (`ai_guard.py`, `engine.py`, `homework.py`, `distill.py`, `rules.py`), accounts and the
feed (`cloud.py`), the Chrome/Edge/Firefox extension (`extension/`), the website.

## What is Mac-only today, and what replaces it on Windows
| Mac piece | Where | Windows replacement |
| --- | --- | --- |
| Reading text boxes and holding Send (Accessibility + event tap) | `watcher.py` (~1200 lines) | UI Automation + a low-level keyboard/mouse hook. Websites can lean on the extension instead |
| The native warning popup (Swift) | `overlay/mac`, `overlay_client.py` | A small native Windows window speaking the same protocol (`overlay/PROTOCOL.md`), or a topmost web window |
| Menu-bar item, app windows | `main.py` | A system-tray icon (pystray) and the same pywebview window |
| Hiding blocked apps | `lock.py` (NSWorkspace) | A foreground-window hook (SetWinEventHook) and minimizing the window |
| Stay alive during a lock-in | `keepalive.py`, `watchdog.py` (launchd) | Task Scheduler entry that relaunches the app |
| Reading text in pictures | `ocr.py` (Apple Vision) | Windows.Media.Ocr (built in) |
| Alerts | `notifier.py` | Windows toast notifications |
| Safari extension, Sparkle updates | `extensions.py`, `sparkle.py` | Not applicable. Updates: WinSparkle or a simple installer-based updater |
| Installer and signing | `build.sh` (PyInstaller, codesign, notarize) | PyInstaller on a Windows build machine, an Inno Setup installer, Authenticode signing |

## Order of work
1. A Windows machine to test on (UTM virtual machine) and a way to run commands in it.
2. Put the Mac-only code behind small modules that load by platform (`platform_info.py` says which).
3. Windows MVP: tray icon + window + extension-based guarding of AI websites, session lock, accounts, feed.
4. Guard desktop AI apps (ChatGPT, Claude apps) with UI Automation.
5. Build the installer automatically on GitHub's Windows machines, sign it, add a download button to the website.

## Open risks
- Typing capture in other apps is the hard part and cannot be fully tested until we run on Windows.
- The AI model will run on the CPU on many laptops, so checks may take several seconds instead of under one.
- Windows installs of `llama-cpp-python` need a prebuilt wheel (CPU build is fine).

## Status (tested in a Windows 11 virtual machine)
| Piece | State |
| --- | --- |
| App window, tray icon, accounts, feed, messages, settings | Working (`winmain.py`) |
| Browser extension (Chrome / Edge / Firefox) and the extension bridge | Working; Safari is hidden on Windows on purpose |
| Warning popup (Edit / Send anyway) | Working (`winoverlay.py`) |
| Watching desktop AI apps: Enter and clicks on a Send button are held, text read with UI Automation, decision, resend | Working with a stand-in "Claude" app (Enter: allow, flag and send anyway tested; Send-click: allow tested); real ChatGPT/Claude apps still to try (`watcher_win.py`) |
| Keyword-rules fallback when the AI is slow | Working: waits 12 s, then uses the keyword rules |
| Lock-in: minimize blocked windows/browsers, bring the guarded browser back | Working (`winlock.py`, rules in `winlockrules.py`, tested) |
| Relaunch after a force-quit during a timed lock-in | Working (Task Scheduler job, `winkeepalive.py`) |
| Reading text in pictures | Working (Windows.Media.Ocr in `ocr.py`) |
| Installer | Built and installed in the VM (`build_win.ps1`, `installer.iss`, `.github/workflows/windows.yml`) |
| Code signing | Not set up (needs an Authenticode certificate; the script signs if CERT_PFX is set) |
| Updates | Update notice reads `version-windows.json` (staged in `release/`); the installer is downloaded by hand |
| Alerts | Tray balloons for now; clicking one does not open the app yet |
| Website download button | Not added (nothing is published) |

Test notes: the virtual machine emulates Intel on an Apple chip, so the AI model is far slower there than on a real PC.
