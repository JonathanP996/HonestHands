# HonestHands

*"Let the thief no longer steal, but rather let him labor, doing honest work with his own hands, so that he may have something to share with anyone in need." — Ephesians 4:28*

A Mac menu-bar app that checks every message you are about to send to an AI against **your class's own rules** and warns you first, so AI stays a tutor and not a shortcut. You can always send anyway; it is just recorded. Optionally, pair up with a friend or mentor who sees when you lock in and any prompt you send despite a warning.

The AI that does the checking is a small built-in model that runs on your Mac. What you type never leaves it.

## How it works

You start a **study session** for a class (and optionally an assignment). While it is on, HonestHands holds each send for a moment and asks "would the professor be comfortable with this?"

- **Your syllabus is the rulebook.** Add a class with its syllabus (PDF, Word, or pasted text). HonestHands pulls out the parts about AI and outside help, word for word, and shows them to you to edit. Assignments can add their own rules.
- **A private checklist.** From those rules the AI builds a short list of "things this policy forbids" and "things it allows", each backed by an exact quote. Each message is matched against that list, which is fast (well under a second) and reliable on a small model.
- **It knows your homework.** The assignment's questions are indexed. A message that pastes, cites ("answer question 3a") or rewords a homework question is caught, while ordinary concept questions about the same topic pass.
- **It reads pictures.** Attach a screenshot of the homework and the browser extension hands it to the app, which reads the text on-device with Apple's Vision framework and judges it like typed text. A picture it cannot read is flagged only if the policy forbids sharing questions or your work.
- **Chrome's Ask Gemini side panel is covered**, along with the Claude and ChatGPT desktop apps (text only) and AI websites (via the extension).
- **Built-in Tutor mode** needs no class: it uses the Joyner AI-assistance heuristics (treat AI like a knowledgeable peer; never copy from the chat; don't keep the assignment and the AI open together).

When a message is flagged you get a popup with the reason, the rule, the exact line it came from, and two buttons: **Edit my message** or **Send it now** (which is recorded as *overridden*).

Outcomes are always one of: **clean**, **flagged** (held), or **overridden** (sent despite a warning).

## Run it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Each new Terminal window: `cd` here and `source .venv/bin/activate` again before `python3 main.py`.

The first launch walks you through setup: macOS **Accessibility** permission (so the guard can read and hold a send), an optional test notification, the one-time ~2 GB download of the AI, your browser and its extension, an optional account, and your first class.

The popup is a small native Swift program. Build it once with `cd overlay/mac && swift build -c release` (the build script does this for you). Without it the app falls back to a simpler built-in panel.

## Build the Mac app + DMG

```
./build.sh
```

This produces **HonestHands.app** and **HonestHands.dmg**. First launch: right-click the app, choose Open (it isn't code-signed yet), then grant Accessibility.

## Using it

- **Study session** — pick a class (or Tutor mode) and an assignment, then start. The session screen shows the timer and this session's clean / flagged / overridden counts.
- **Classes** — add classes and assignments; click one to see its AI rules. Each class has its own color.
- **Activity** — every check, newest first, filterable by outcome, with paging.
- **History** — your sessions as large blocks, grouped by day. Click one to see every prompt from that session.
- **Insights** — clean rate, time locked in, where you use AI, a streak calendar, time per class, and your week.
- **Community** — create an account (email and password), then invite people by handle. One-way or mutual. They see only: prompts you sent despite a warning (with their text), session times, daily counts, and when the app last checked in. Never your syllabi, assignments, or the text of clean or flagged messages. Turn "Share my activity" off at any time.
- **Settings** — the AI's status, your guarded browser and its extension, an optional accountability PIN (a friend sets it, then ending a session, deleting a class or clearing the log needs it), and permissions.

## Your guarded browser (and the extension)

During a study session you pick **one browser** for AI: Chrome, Edge, Firefox or Safari. **AI websites in every other browser are blocked** (the send is held with a "switch to <your browser>" message), so there is no easy way around the guard. The Claude and ChatGPT desktop apps are covered by the Mac app directly.

Some AI websites hide their send button from macOS, and only the page itself can see attached pictures, so a small extension runs in your chosen browser. It does nothing unless HonestHands is running and a session is on; all rules, judging and logging stay in the app.

| Browser | How it is installed |
| --- | --- |
| Chrome, Edge | The same extension (Manifest V3). Copy the files, open the extensions page, Developer mode, **Load unpacked**. |
| Firefox | Same code with a Manifest V2 file the app generates. **Load Temporary Add-on** on `about:debugging`. Firefox forgets temporary add-ons when it quits, so re-load it after a restart until we publish a signed one. |
| Safari | The app builds a small helper app with Xcode (free) and Apple's converter. Open it once, then Safari › Settings › Advanced › Show features for web developers, Develop › Allow Unsigned Extensions, and switch the extension on under Settings › Extensions. |

Set it up in the first-run flow or in **Settings › Guarded browser**. After updating the app, refresh the extension in your browser and reload your AI tabs.

## Community setup (Supabase)

Accounts, partners and the feed use a Supabase project. The database layout and the access rules are in `cloud/schema.sql`; the one-time setup steps are in `cloud/README.md`. In short: run `schema.sql`, turn off "Confirm email", and put the project URL and the public anon key in `cloud.py` (or the `HH_SUPABASE_URL` / `HH_SUPABASE_ANON` environment variables). Never put the `service_role` key anywhere in this repo.

## Tests

```
python3 tests/run_guard_tests.py   # the real guard on ~46 exact messages; appends to tests/results.jsonl
python3 tests/test_homework.py     # finding which homework question a message resembles
python3 tests/test_images.py       # pictures read on-device and judged
python3 tests/test_browser_block.py # AI sites are blocked in every browser except the guarded one
python3 tests/test_cloud_mock.py   # accounts, partners, sync, against an in-memory stand-in for Supabase
```

When the guard gets something wrong, paste the exact message into `tests/guard_cases.json` with the result you expected. See `tests/README.md`.

## Privacy

- The AI runs locally; nothing you type is sent to a model provider.
- Your log, classes and settings live in `~/Library/Application Support/HonestHands/` (the config file is readable only by you).
- If you sign in to Community, only overridden prompts (with text) and counts are uploaded. See `cloud/schema.sql`: the database itself refuses to store the text of anything else.

## Known limits

- Honor system plus accountability: someone determined can quit the app. A partner sees "Quiet since…" when check-ins stop.
- Pictures are read only through the browser extension, and only if the site shows a thumbnail in the page. The Claude and ChatGPT desktop apps are text-only.
- The other-browser block holds sends; it does not stop you reading an AI site in another browser, and a system-wide web block would need administrator access.
- Firefox's extension is temporary until we publish a signed one; Safari's is for local use until we sign it with a paid Apple developer account.
- Handwriting and photos with no readable text are flagged only when the policy forbids sharing questions or your work.
- Ask Gemini can also read the open web page; a message like "answer the question on this page" does not mention the homework, so the guard cannot match it.
- It covers desktop AI apps and AI websites on a Mac, not phones or AI built into other apps yet.

## Layout

| File | What it does |
| --- | --- |
| `main.py` | App entry, menu bar, windows |
| `watcher.py` | Reads your message through Accessibility and holds the send |
| `ai_guard.py` | The guard: checklist, homework matching, pictures |
| `engine.py` | The on-device AI model |
| `browsers.py`, `extensions.py` | The supported browsers; building the extension for each |
| `homework.py` | Finds which homework question a message resembles |
| `ocr.py` | Reads text in pictures (Apple Vision) |
| `distill.py`, `docs.py`, `rules.py` | Pulling the AI rules out of a syllabus; keyword fallback |
| `cloud.py` | Account, partners, background sync |
| `overlay/` | The native popup and its protocol |
| `extension/` | The browser extension |
| `ui/` | The app's screens |
| `cloud/` | Database schema and setup notes |
| `tests/` | The regression suite |
