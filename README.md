# HonestHands

*"Let the thief no longer steal, but rather let him labor, doing honest work with his own hands, so that he may have something to share with anyone in need." — Ephesians 4:28*

A menu-bar app that checks every message you're about to send to an AI (the Claude and ChatGPT desktop apps, and AI websites in any browser) against your class's real syllabus rules, and warns or blocks before it sends. The AI "judge" runs on your Mac, so your messages, syllabus, and assignments never leave the computer.

## Run it (to try it now)

From this folder in Terminal:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

After the second line your prompt shows `(.venv)` — that's the app's own environment. Each new Terminal window: `cd` here and run `source .venv/bin/activate` again before `python3 main.py`.

The first launch asks for **Accessibility** permission (System Settings › Privacy & Security › Accessibility). That's what lets the guard read and hold your messages. Grant it, then reopen.

## Build the Mac app + DMG (to install it properly)

```
./build.sh
```

This produces **HonestHands.app** and **HonestHands.dmg**. Open the DMG, drag the app to Applications. First launch: right-click the app › Open (it isn't code-signed), then grant Accessibility.

## Using it

1. **Settings › The AI judge** — the built-in AI downloads once (engine + a small model, ~2 GB). Or pick Ollama, or keyword-rules-only (no download).
2. **Classes › Add a class** — give it the syllabus (PDF, Word, or pasted text). The AI reads the AI-use rules and shows each one with the exact line it came from. Review and save.
3. Add assignments if you like; their rules apply on top of the class rules.
4. **Try the judge** — test messages and run the accuracy check before relying on it.
5. **Study session** — pick a class and start. Use AI as normal; each message is checked the instant before it sends.

## Notes

- Keyword rules run first and instantly; the AI judge handles the rest and pre-checks your draft while you type, so sending feels immediate. If the AI isn't ready, it falls back to keyword rules rather than freezing your keyboard.
- Optional accountability PIN (Settings): a parent or partner sets it, and then loosening or clearing anything needs it. Export a report from Activity. Remove it in Settings › Accountability PIN with the current PIN. Forgotten PIN (e.g. during development): start once with `HH_RESET_PIN=1 python3 main.py`.
- Covers AI desktop apps and AI websites in browsers, not phones or AI built into other apps yet.
- It's an honor-system tool; it works best paired with someone who sees your reports.


## Browser extension (for AI websites)

Some AI **websites** (Gemini especially) hide their send button from macOS, so the Mac app can't catch button-clicks there on its own. A tiny companion extension fixes this. It is deliberately "dumb": it only watches the page and asks the desktop app for a verdict. **It does nothing unless HonestHands is running and a study session is active.** All rules, judging, logging, and the warning panel stay in the app.

Set it up in **Settings › Browser extension**:
1. Click **Set up the extension** (copies the files to a stable folder).
2. Open your browser's Extensions page, turn on **Developer mode**, click **Load unpacked**, and choose that folder.
3. Enable it once — it stays on after that.

Desktop AI apps (Claude app, ChatGPT app) are covered by the Mac app directly and don't need the extension.
