"""Watches AI apps and sites: reads your prompt through Accessibility and holds the
Enter key or send-button click until the judge has checked it."""
import re
import subprocess
import time
from urllib.parse import urlparse

from AppKit import (
    NSAlert,
    NSApplication,
    NSApplicationActivateIgnoringOtherApps,
    NSRunningApplication,
    NSWorkspace,
)
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    AXUIElementCopyAttributeValue,
    AXUIElementCopyElementAtPosition,
    AXUIElementCreateApplication,
    AXUIElementCreateSystemWide,
    AXUIElementGetPid,
    AXUIElementSetAttributeValue,
    AXUIElementSetMessagingTimeout,
)
from CoreFoundation import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopRun,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    kCFRunLoopCommonModes,
)
from PyObjCTools import AppHelper
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventCreateMouseEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSetIntegerValueField,
    CGPointMake,
    kCGEventLeftMouseUp,
    kCGEventSourceUserData,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGMouseEventClickState,
    CGWindowListCopyWindowInfo,
    kCGNullWindowID,
    kCGWindowListExcludeDesktopElements,
    kCGWindowListOptionOnScreenOnly,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventGetLocation,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
    kCGEventKeyDown,
    kCGEventLeftMouseDown,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGEventTapOptionDefault,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)

import os
import rules
import threading

AIG_DEBUG = os.environ.get('AIG_DEBUG') == '1'


def dbg(*a):
    if AIG_DEBUG:
        print('[guard]', *a, flush=True)

try:
    from ApplicationServices import kAXTrustedCheckOptionPrompt
except ImportError:
    kAXTrustedCheckOptionPrompt = 'AXTrustedCheckOptionPrompt'

# ---------------- What counts as "AI" ----------------
AI_DOMAINS = [
    'chatgpt.com', 'chat.openai.com', 'claude.ai', 'claude.com', 'gemini.google.com', 'aistudio.google.com',
    'notebooklm.google.com', 'copilot.microsoft.com', 'copilot.cloud.microsoft', 'm365.cloud.microsoft',
    'perplexity.ai', 'chat.deepseek.com', 'grok.com', 'x.ai', 'poe.com', 'meta.ai', 'chat.mistral.ai',
    'you.com', 'character.ai', 'chat.qwen.ai', 'kimi.com', 'kimi.ai', 'pi.ai', 'huggingface.co',
    'quillbot.com', 'phind.com', 'chat.z.ai', 'duck.ai',
]
# Any app whose name or bundle ID contains one of these counts as an AI app.
AI_APP_KEYWORDS = ['claude', 'chatgpt', 'openai', 'gemini', 'perplexity', 'copilot', 'deepseek',
                   'grok', 'mistral', 'poe', 'qwen', 'kimi', 'quillbot']
BROWSERS = {
    'com.apple.Safari', 'com.apple.SafariTechnologyPreview', 'com.google.Chrome', 'com.google.Chrome.canary',
    'com.google.Chrome.beta', 'com.microsoft.edgemac', 'com.microsoft.edgemac.Beta', 'com.brave.Browser',
    'company.thebrowser.Browser', 'company.thebrowser.dia', 'org.mozilla.firefox', 'org.mozilla.firefoxdeveloperedition',
    'com.operasoftware.Opera', 'com.operasoftware.OperaGX', 'com.vivaldi.Vivaldi', 'org.chromium.Chromium',
    'app.zen-browser.zen', 'com.kagi.kagimacOS', 'com.duckduckgo.macos.browser', 'ai.perplexity.comet',
    'com.openai.atlas', 'com.sigmaos.sigmaos.macos', 'net.waterfox.waterfox',
}
CHROMIUM_LIKE = {
    'com.google.Chrome', 'com.google.Chrome.canary', 'com.google.Chrome.beta', 'com.microsoft.edgemac',
    'com.microsoft.edgemac.Beta', 'com.brave.Browser', 'company.thebrowser.Browser', 'company.thebrowser.dia',
    'com.operasoftware.Opera', 'com.operasoftware.OperaGX', 'com.vivaldi.Vivaldi', 'org.chromium.Chromium',
    'ai.perplexity.comet', 'com.openai.atlas', 'com.sigmaos.sigmaos.macos',
}
TITLE_HINTS = re.compile(r'\b(ChatGPT|Claude|Gemini|AI Studio|NotebookLM|Copilot|Perplexity|DeepSeek|Grok|'
                         r'Le Chat|Mistral|Poe|Character\.AI|Qwen|Kimi|QuillBot|Meta AI)\b', re.I)
TEXT_ROLES = {'AXTextArea', 'AXTextField', 'AXComboBox', 'AXSearchField'}

ENTER_KEYS = (36, 76)  # Return, keypad Enter


# ---------------- Accessibility helpers ----------------
def ax(el, attr):
    if el is None:
        return None
    try:
        err, val = AXUIElementCopyAttributeValue(el, attr, None)
    except Exception:
        return None
    return val if err == 0 else None


def _frame_of(el):
    """Screen rect (x, y, w, h) of an element, or None."""
    if el is None:
        return None
    try:
        from ApplicationServices import AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType
        from Quartz import CGPoint, CGSize
        pos = ax(el, 'AXPosition')
        size = ax(el, 'AXSize')
        if pos is None or size is None:
            return None
        okp, pt = AXValueGetValue(pos, kAXValueCGPointType, CGPoint())
        oks, sz = AXValueGetValue(size, kAXValueCGSizeType, CGSize())
        if not okp or not oks:
            return None
        return (float(pt.x), float(pt.y), float(sz.width), float(sz.height))
    except Exception:
        return None



def front_app():
    """The app you're typing in right now: whoever owns the topmost normal window.
    This stays current even outside a Cocoa run loop (NSWorkspace does not)."""
    try:
        wins = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID) or []
        for w in wins:
            if w.get('kCGWindowLayer', 1) == 0:
                app = NSRunningApplication.runningApplicationWithProcessIdentifier_(w.get('kCGWindowOwnerPID'))
                if app is not None:
                    return app
    except Exception:
        pass
    # Fallback: ask Accessibility.
    sysel = AXUIElementCreateSystemWide()
    AXUIElementSetMessagingTimeout(sysel, 0.3)
    focused_app = ax(sysel, 'AXFocusedApplication')
    if focused_app is not None:
        err, pid = AXUIElementGetPid(focused_app, None)
        if err == 0:
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app is not None:
                return app
    return NSWorkspace.sharedWorkspace().frontmostApplication()


def app_info(app):
    return (str(app.bundleIdentifier() or ''), str(app.localizedName() or ''), app.processIdentifier())


def is_ai_app(bid, name):
    if bid in BROWSERS:
        return False  # browsers are judged by the website instead
    hay = f'{bid} {name}'.lower()
    return any(k in hay for k in AI_APP_KEYWORDS)


def watchable(app):
    bid, name, _ = app_info(app)
    return bid in BROWSERS or is_ai_app(bid, name)


_woken = set()


def wake_accessibility(app):
    """Ask Chrome-based browsers and Electron apps to share their page text."""
    bid, name, pid = app_info(app)
    if pid in _woken or not (bid in CHROMIUM_LIKE or is_ai_app(bid, name)):
        return
    el = AXUIElementCreateApplication(pid)
    for attr in ('AXManualAccessibility', 'AXEnhancedUserInterface'):
        try:
            AXUIElementSetAttributeValue(el, attr, True)
        except Exception:
            pass
    _woken.add(pid)


def _is_editable(el):
    if el is None:
        return False
    role = ax(el, 'AXRole')
    if role in TEXT_ROLES:
        return True
    # Rich-text editors (Gemini, Claude, ChatGPT) expose contenteditable areas with
    # roles like AXGroup/AXTextArea and a settable AXValue or an editable subrole.
    sub = ax(el, 'AXSubrole')
    if sub in ('AXContentEditable', 'AXTextArea'):
        return True
    rd = str(ax(el, 'AXRoleDescription') or '').lower()
    if 'edit' in rd or 'text' in rd:
        # confirm it actually holds editable text
        if ax(el, 'AXValue') is not None or role in ('AXGroup', 'AXTextArea', 'AXWebArea'):
            return True
    return False


def text_box(el):
    """The text box itself. The focused element may be the box, something inside it,
    or a wrapper around it, so we search a few parents and then a shallow subtree."""
    node = el
    for _ in range(5):          # climb parents
        if node is None:
            break
        if _is_editable(node):
            return node
        node = ax(node, 'AXParent')

    # Not found climbing: look a little way DOWN from the focused element.
    def descend(n, depth):
        if n is None or depth > 4:
            return None
        if _is_editable(n) and depth > 0:
            return n
        for child in (ax(n, 'AXChildren') or [])[:40]:
            found = descend(child, depth + 1)
            if found is not None:
                return found
        return None

    return descend(el, 0)


def read_text(el):
    val = ax(el, 'AXValue')
    if isinstance(val, str) and val.strip():
        return str(val)
    parts = []

    def collect(node, depth):
        if node is None or depth > 6 or len(parts) > 400:
            return
        if ax(node, 'AXRole') == 'AXStaticText':
            v = ax(node, 'AXValue')
            if isinstance(v, str):
                parts.append(str(v))
        for child in ax(node, 'AXChildren') or []:
            collect(child, depth + 1)

    collect(el, 0)
    return '\n'.join(parts)


def page_url(el):
    """Walk up from the text box to the web page and read its address."""
    for _ in range(120):
        if el is None:
            return None
        if ax(el, 'AXRole') == 'AXWebArea':
            u = ax(el, 'AXURL')
            if u is None:
                return None
            return str(u.absoluteString()) if hasattr(u, 'absoluteString') else str(u)
        parent = ax(el, 'AXParent')
        # Some web views expose the URL on the window/scroll area instead; check AXURL too.
        if parent is None:
            u = ax(el, 'AXURL')
            if u is not None:
                return str(u.absoluteString()) if hasattr(u, 'absoluteString') else str(u)
        el = parent
    return None


def ai_domain(url):
    host = (urlparse(url).hostname or '').lower()
    for d in AI_DOMAINS:
        if host == d or host.endswith('.' + d):
            return d
    return None


def where_am_i(app, box, appel):
    """Returns a label like 'claude.ai' or 'ChatGPT app' if this is an AI context, else None."""
    bid, name, _ = app_info(app)
    url = page_url(box)
    if url:
        d = ai_domain(url)
        if d:
            return d
        if bid in BROWSERS:
            return None  # a normal website
    if is_ai_app(bid, name):
        return f'{name} app'
    if bid in BROWSERS:
        # Couldn't read the address: fall back to the window title.
        title = ax(ax(appel, 'AXFocusedWindow'), 'AXTitle') or ''
        m = TITLE_HINTS.search(str(title))
        if m:
            return f'{m.group(1)} (from window title, {name})'
    return None


PLACEHOLDERS = {
    'ask gemini', 'ask anything', 'message chatgpt', 'ask chatgpt', 'send a message',
    'how can i help you today', 'reply to claude', 'message claude', 'ask claude',
    'type a message', 'enter a prompt', 'write something', 'new chat', 'claude',
    'ask copilot', 'message copilot', 'ask perplexity', 'ask anything...', 'how can i help?',
}

# Attributes that identify the ADDRESS BAR / search field, which must never be treated as a composer.
ADDRESS_BAR_HINTS = re.compile(
    r'(address and search bar|type a url|ask google or type|search or enter|'
    r'press tab then enter|address bar|search bar|omnibox)', re.I)

# Per-site profiles. For each AI site we match the composer by its accessibility label
# (AXDescription / AXTitle / AXPlaceholderValue), which your scan showed is stable.
# The send button has no reliable label on these sites, so we guard the send GESTURE
# (Enter, or a click low in the composer region) instead of pinpointing the button.
SITE_PROFILES = {
    'gemini.google.com': {'composer': re.compile(r'enter a prompt for gemini|ask gemini', re.I)},
    'chatgpt.com':       {'composer': re.compile(r'chat with chatgpt|ask chatgpt|message chatgpt', re.I)},
    'chat.openai.com':   {'composer': re.compile(r'chat with chatgpt|ask chatgpt|message chatgpt', re.I)},
    'claude.ai':         {'composer': re.compile(r'write your prompt to claude|message claude|reply to claude', re.I)},
    'claude.com':        {'composer': re.compile(r'write your prompt to claude|message claude|reply to claude', re.I)},
    'copilot.microsoft.com': {'composer': re.compile(r'ask copilot|message copilot|chat with copilot', re.I)},
    'perplexity.ai':     {'composer': re.compile(r'ask anything|ask follow-?up', re.I)},
    'chat.deepseek.com': {'composer': re.compile(r'message deepseek|send a message|ask deepseek', re.I)},
    'grok.com':          {'composer': re.compile(r'ask grok|message grok|ask anything', re.I)},
    'meta.ai':           {'composer': re.compile(r'ask meta ai|message meta|ask anything', re.I)},
}


def _label_of(el):
    return ' '.join(str(ax(el, a) or '') for a in
                    ('AXDescription', 'AXTitle', 'AXPlaceholderValue', 'AXRoleDescription'))


def _is_address_bar(el):
    return bool(ADDRESS_BAR_HINTS.search(_label_of(el)))


def find_profiled_composer(appel, where):
    """Find the composer for a known site by its stable label. Returns the element or None."""
    prof = SITE_PROFILES.get(where)
    if not prof:
        return None
    pat = prof['composer']
    win = ax(appel, 'AXFocusedWindow') or ax(appel, 'AXMainWindow')
    if win is None:
        return None
    best = [None]

    def scan(node, depth):
        if node is None or depth > 24 or best[0] is not None:
            return
        role = ax(node, 'AXRole')
        if role in ('AXTextArea', 'AXTextField') or _is_editable(node):
            if not _is_address_bar(node) and pat.search(_label_of(node)):
                best[0] = node
                return
        for child in (ax(node, 'AXChildren') or [])[:70]:
            scan(child, depth + 1)
            if best[0] is not None:
                return

    scan(win, 0)
    return best[0]


def _looks_placeholder(t):
    return t.strip().lower() in PLACEHOLDERS


def find_composer(appel, focused):
    """Locate the message composer. Prefer the focused text box; if focus has moved to the
    send button, search the focused window for the composer text area instead."""
    box = text_box(focused)
    if box is not None:
        return box
    # Focus isn't on a text box (e.g. the send button is focused). Search the window.
    win = ax(focused, 'AXWindow') or ax(appel, 'AXFocusedWindow') or ax(appel, 'AXMainWindow')
    if win is None:
        return None

    best = [None]

    def scan(node, depth):
        if node is None or depth > 22 or best[0] is not None:
            return
        role = ax(node, 'AXRole')
        if role in ('AXTextArea', 'AXTextField') or _is_editable(node):
            best[0] = node
            return
        for child in (ax(node, 'AXChildren') or [])[:60]:
            scan(child, depth + 1)
            if best[0] is not None:
                return

    scan(win, 0)
    return best[0]


_LAST = {'where': None, 'text': '', 'pid': None, 't': 0.0}


def current_prompt(retries=3):
    """What you're about to send, or None if not in an AI context. Searches the window for
    the composer so a click on Send is caught, and remembers the last non-empty text so a
    box that clears the instant you hit send is still checked."""
    app = front_app()
    if app is None or not watchable(app):
        return None
    wake_accessibility(app)
    bid, name, pid = app_info(app)
    appel = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(appel, 0.4)

    where = None
    text = ''
    for attempt in range(max(1, retries)):
        focused = ax(appel, 'AXFocusedUIElement')
        # First figure out where we are (needs some element to read the URL from).
        probe = focused
        if _is_address_bar(focused):
            probe = None  # don't let the URL bar decide the site
        box = find_composer(appel, focused)
        where = where_am_i(app, box or probe or focused, appel)
        if where is None:
            return None  # a normal website, not an AI context

        # Prefer the site's known composer; fall back to the generic finder.
        pbox = find_profiled_composer(appel, where)
        if pbox is not None:
            box = pbox
        # Never read the address bar as the composer.
        if box is not None and _is_address_bar(box):
            box = None

        if box is not None:
            text = read_text(box).strip()
        if not text and focused is not None and not _is_address_bar(focused):
            text = read_text(focused).strip()
        if _looks_placeholder(text):
            text = ''
        if text:
            break
        time.sleep(0.04)

    now = time.time()
    if text:
        _LAST.update(where=where, text=text, pid=pid, t=now)
    elif (_LAST['text'] and _LAST['pid'] == pid and _LAST['where'] == where
          and now - _LAST['t'] < 1.5):
        # The composer just cleared (sent). Use what we saw a moment ago.
        text = _LAST['text']

    return {'where': where, 'text': text, 'pid': pid, 'app': name}


def remember_typed():
    """Called by the typing-watch loop so the 'last text' is fresh at the moment of send."""
    try:
        current_prompt(retries=1)
    except Exception:
        pass


def notify(title, message):
    subprocess.Popen(['osascript', '-e', f'display notification {applescript_str(message)} with title {applescript_str(title)}'])


def applescript_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def has_accessibility(prompt=False):
    try:
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))
    except Exception:
        return False


def open_accessibility_settings():
    subprocess.Popen(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])



# ---------------- The guard ----------------
MARK = 0x41494721  # tags the Enter/click we re-send ourselves, so we don't check it twice


class Guard:
    def __init__(self, store, judge):
        self.store, self.judge = store, judge
        self.tap = None
        self.bypass_until = 0
        self.bypass_pid = None
        self.locked = False            # True = a send is being held; swallow everything until resolved
        self._entry = threading.Lock() # serializes the decision so two quick clicks can't both pass

    @property
    def watching(self):
        return self.tap is not None

    # ---- setup (main thread) ----
    def install(self):
        if self.tap is not None:
            return True
        # Run the keyboard/mouse tap on its OWN run loop thread. If it lived on the
        # main thread, a modal warning dialog would spin the main run loop and stop
        # the tap from firing — which let Enter slip through while the warning was up.
        result = {'ok': None}
        ready = threading.Event()

        def run():
            mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventLeftMouseDown)
            tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionDefault,
                                   mask, self.on_event, None)
            if tap is None:
                result['ok'] = False
                ready.set()
                return
            src = CFMachPortCreateRunLoopSource(None, tap, 0)
            CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes)
            CGEventTapEnable(tap, True)
            self.tap = tap
            result['ok'] = True
            ready.set()
            CFRunLoopRun()  # keeps processing events on this thread forever

        threading.Thread(target=run, daemon=True).start()
        ready.wait(timeout=5)
        return bool(result['ok'])

    def start_typing_watch(self):
        """While you type in an AI app, checks your draft whenever you pause."""
        def loop():
            last_text, since = None, 0.0
            while True:
                time.sleep(0.5)
                try:
                    cls, asg = self.store.session_targets()
                    if not cls or self.locked:
                        last_text = None
                        continue
                    p = current_prompt()  # also refreshes the last-seen text cache
                    if not p or len(p['text']) < 3:
                        last_text = None
                        continue
                    if not self.judge.engine.ready():
                        continue  # cache is kept fresh above; AI pre-check needs the engine
                    if p['text'] != last_text:
                        last_text, since = p['text'], time.time()
                    elif time.time() - since >= 0.8:
                        self.judge.prejudge(p['text'], cls, asg, p['where'])
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()

    # ---- the event tap ----
    def on_event(self, proxy, etype, event, refcon):
        if etype in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            CGEventTapEnable(self.tap, True)
            return event
        try:
            if CGEventGetIntegerValueField(event, kCGEventSourceUserData) == MARK:
                return event
            cls, asg = self.store.session_targets()
            if not cls:
                return event
            hook = Guard.overlay_hook
            if self.locked and hook is not None and hook.is_open():
                if etype == kCGEventLeftMouseDown:
                    pt = CGEventGetLocation(event)
                    if hook.owns_point(pt.x, pt.y):
                        return event      # a click on the warning itself: never swallow it
                elif etype == kCGEventKeyDown:
                    kc = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                    if kc == 53:
                        hook.choose('edit'); return None
                    if kc in ENTER_KEYS:
                        cmd = bool(CGEventGetFlags(event) & kCGEventFlagMaskCommand)
                        hook.choose('send_anyway' if cmd else 'edit'); return None
            if etype == kCGEventKeyDown:
                kc = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                if kc not in ENTER_KEYS:
                    return event
                flags = CGEventGetFlags(event)
                if flags & (kCGEventFlagMaskShift | kCGEventFlagMaskAlternate):
                    dbg('Enter with shift/alt -> ignored (newline)')
                    return event
                dbg('ENTER seen, keycode', kc, '- intercepting')
                allow = self.intercept('enter', None, cls, asg)
                dbg('ENTER decision:', 'ALLOW/through' if allow else 'HELD')
                return event if allow else None
            if etype == kCGEventLeftMouseDown:
                is_send = self.click_is_send(event)
                dbg('click; is_send =', is_send)
                if is_send:
                    pt = CGEventGetLocation(event)
                    allow = self.intercept('click', (pt.x, pt.y), cls, asg)
                    dbg('CLICK decision:', 'ALLOW/through' if allow else 'HELD')
                    return event if allow else None
        except Exception as e:  # never freeze the keyboard over a bug
            print(f'guard error, letting it through: {e}')
        return event

    def intercept(self, trigger, loc, cls, asg):
        """True = let it through now. False = hold it. Locks on the very first event
        so a rapid second click/Enter can't race past before the warning appears."""
        # If anything is already being held, swallow this immediately.
        if self.locked:
            return False
        # Grab the decision lock without blocking the tap thread; if we can't, hold.
        if not self._entry.acquire(blocking=False):
            return False
        self.locked = True
        self._held = (trigger, loc)
        try:
            p = current_prompt()
            dbg('intercept: where=', (p or {}).get('where'), 'text=', repr((p or {}).get('text','')[:60]))
            if not p or not p['text']:
                dbg('intercept: no text -> ALLOW')
                self._release()
                return True
            if time.time() < self.bypass_until and p['pid'] == self.bypass_pid:
                self.bypass_until = 0
                self.record(p, cls, asg, trigger, 'sent after warning', None)
                self._release()
                return True

            r = self.judge.cached(p['text'], cls, asg)
            if r is None and (rules.check(p['text'], cls, asg).get('evade') or not self.judge.engine.ready()):
                r = self.judge.check(p['text'], cls, asg, p['where'])  # no AI, instant
            if r is not None:
                dbg('intercept: cached/instant verdict =', r.get('verdict'), 'level=', r.get('level'))
                return self.act(r, p, cls, asg, trigger)  # releases on allow; stays locked on flag
            dbg('intercept: no cached verdict -> async AI judge, HOLDING')

            # Need the AI. Stay locked, judge in the background, decide in _finish.
            threading.Thread(target=self._judge_then_send, args=(p, cls, asg, trigger, loc), daemon=True).start()
            return False
        except Exception as e:
            print(f'guard error, letting it through: {e}')
            self._release()
            return True

    def _release(self):
        self.locked = False
        if self._entry.locked():
            try:
                self._entry.release()
            except RuntimeError:
                pass

    def _judge_then_send(self, p, cls, asg, trigger, loc):
        try:
            r = self.judge.check(p['text'], cls, asg, p['where'], timeout=10)
            dbg('async judge done: verdict=', r.get('verdict'), 'level=', r.get('level'), 'source=', r.get('source'))
        except Exception as e:
            dbg('async judge ERROR:', e, '-> defaulting')
            r = dict(rules.check(p['text'], cls, asg), source='keywords', note=str(e))
            r['verdict'] = 'allow' if r['level'] != 'flag' else 'warn'
        AppHelper.callAfter(self._finish, r, p, cls, asg, trigger, loc)

    def _finish(self, r, p, cls, asg, trigger, loc):
        dbg('_finish: level=', r['level'], 'verdict=', r.get('verdict'))
        if r['level'] not in ('ok', 'note'):
            # Flagged: show the warning (stays locked until the dialog is closed).
            hard = self.is_hard(r)
            dbg('_finish: FLAGGED -> showing warning (hard=', hard, ')')
            self.record(p, cls, asg, trigger, 'blocked' if hard else 'warned', r)
            AppHelper.callAfter(self.show_warning, r, hard, p, cls, asg)
            return
        # Allowed: record, unlock, and actually send it for the user.
        self.record(p, cls, asg, trigger, 'ok (disclose)' if r['level'] == 'note' else 'ok', r)
        if r['level'] == 'note' and r.get('reasons'):
            notify('HonestHands', r['reasons'][0])
        dbg('_finish: ALLOWED -> releasing and re-sending')
        front = front_app()
        same = front is not None and front.processIdentifier() == p['pid']
        self._release()
        if not same:
            notify('HonestHands', 'Your message passed the check but wasn\'t sent because you switched apps. Send it again.')
            return
        self.resend(trigger, loc)

    def is_hard(self, r):
        return False   # one behaviour for everything: warn, with Edit / Send it now (logged)

    def act(self, r, p, cls, asg, trigger):
        if r['level'] in ('ok', 'note'):
            self.record(p, cls, asg, trigger, 'ok (disclose)' if r['level'] == 'note' else 'ok', r)
            if r['level'] == 'note' and r.get('reasons'):
                notify('HonestHands', r['reasons'][0])
            self._release()
            return True
        hard = self.is_hard(r)
        self.record(p, cls, asg, trigger, 'blocked' if hard else 'warned', r)
        AppHelper.callAfter(self.show_warning, r, hard, p, cls, asg)  # stays locked until closed
        return False

    def resend(self, trigger, loc):
        if trigger == 'enter':
            for down in (True, False):
                ev = CGEventCreateKeyboardEvent(None, 36, down)
                CGEventSetFlags(ev, 0)
                CGEventSetIntegerValueField(ev, kCGEventSourceUserData, MARK)
                CGEventPost(kCGHIDEventTap, ev)
        else:
            pt = CGPointMake(loc[0], loc[1])
            for kind in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
                ev = CGEventCreateMouseEvent(None, kind, pt, kCGMouseButtonLeft)
                CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
                CGEventSetIntegerValueField(ev, kCGEventSourceUserData, MARK)
                CGEventPost(kCGHIDEventTap, ev)

    def record(self, p, cls, asg, trigger, result, r):
        entry = {'t': time.time(), 'where': p['where'], 'class': cls['name'],
                 'assignment': asg['name'] if asg else '', 'trigger': trigger,
                 'text': p['text'][:300], 'result': result}
        if r:
            entry['source'] = r.get('source')
            entry['ms'] = r.get('ms')
            if r.get('note'):
                entry['note'] = r['note']
            if r.get('level') == 'flag':
                entry['reasons'] = r.get('reasons')
        self.store.log(entry)

    # The app sets this: fn(guard, r, hard, p, cls, asg) -> shows the block IN the app window.
    block_handler = None
    overlay_hook = None   # set by the app: is_open(), owns_point(x, y), choose(choice)

    def show_warning(self, r, hard, p, cls, asg):
        try:
            if Guard.block_handler is not None:
                AppHelper.callAfter(Guard.block_handler, self, r, hard, p, cls, asg)
                return
        except Exception as e:
            print(f'block handler error, releasing: {e}')
        self._release()

    def on_panel_choice(self, choice, p):
        # choice: 'edit' or 'send_anyway'
        ev = p.get('event')
        if ev is not None:                       # browser-extension path: hand the answer back
            p['choice'] = choice
            ev.set()
            return
        held, self._held = getattr(self, '_held', None), None
        if choice == 'send_anyway':
            cls, asg = self.store.session_targets()
            if cls:
                self.record(p, cls, asg, 'overlay', 'sent anyway', None)
                self.sent_anyway = (p.get('text', ''), time.time() + 20)
            front = front_app()
            same = front is not None and front.processIdentifier() == p.get('pid')
            self._release()
            if held and same:
                trigger, loc = held
                threading.Timer(0.35, lambda: self.resend(trigger, loc)).start()
            return
        self._release()

    SEND_WORDS = re.compile(r'\b(send|submit|ask|run|go|enter|generate|prompt|message|search)\b', re.I)
    SEND_GLYPHS = ('\u2191', '\u2197', '\u27a4', '\u2b06', '\u279c', '\u25b6', '\u21e7', '\u2b95')  # arrows/paper-plane-ish

    def click_is_send(self, event):
        """True if this click is plausibly a 'send'. Sites build send buttons in many
        ways (icon-only, custom markup), so we accept several signals and, as a last
        resort, any clickable control sitting next to the composer text box."""
        app = front_app()
        if app is None or not watchable(app):
            return False
        pt = CGEventGetLocation(event)
        sysel = AXUIElementCreateSystemWide()
        AXUIElementSetMessagingTimeout(sysel, 0.3)
        err, el = AXUIElementCopyElementAtPosition(sysel, pt.x, pt.y, None)
        if err != 0 or el is None:
            return False

        node = el
        clickable = None
        chain = []
        for _ in range(6):
            if node is None:
                break
            role = ax(node, 'AXRole')
            label = ' '.join(str(ax(node, a) or '') for a in
                             ('AXDescription', 'AXTitle', 'AXHelp', 'AXIdentifier', 'AXRoleDescription', 'AXValue'))
            chain.append(f'{role}:{label[:30]!r}')
            if role in ('AXButton', 'AXLink', 'AXPopUpButton', 'AXMenuButton', 'AXImage', 'AXStaticText', 'AXGroup'):
                if self.SEND_WORDS.search(label):
                    dbg('click_is_send: matched SEND word in', repr(label[:40]))
                    return True
                if any(g in label for g in self.SEND_GLYPHS):
                    dbg('click_is_send: matched send glyph')
                    return True
                if role in ('AXButton', 'AXLink', 'AXMenuButton') and clickable is None:
                    clickable = node
            node = ax(node, 'AXParent')
        dbg('click_is_send: cursor chain =', ' < '.join(chain))
        dbg('click_is_send: clickable control found =', clickable is not None)

        # Fallback: AI-site send buttons usually have NO readable label (your scans showed
        # "group" / icon-only). So when there's unsent text and the click lands in the
        # composer's horizontal band (right side, where send sits) or on any control there,
        # treat it as a send gesture.
        p = current_prompt()
        if not p or not p['text']:
            dbg('click_is_send: no unsent text -> not a send')
            return False
        # Position check FIRST: the click must land in/near the composer box. This is what
        # keeps unrelated buttons (DevTools' X, tab close, page buttons far from the
        # composer) from being mistaken for "send", even when a draft is sitting there.
        try:
            _, _, pid = app_info(app)
            appel = AXUIElementCreateApplication(pid)
            AXUIElementSetMessagingTimeout(appel, 0.3)
            box = find_profiled_composer(appel, p['where']) or find_composer(appel, ax(appel, 'AXFocusedUIElement'))
            rect = _frame_of(box)
            dbg('click_is_send: click at', (round(pt.x), round(pt.y)), 'composer rect =',
                tuple(round(v) for v in rect) if rect else None)
            if rect is not None:
                bx, by, bw, bh = rect
                if (bx - 20) <= pt.x <= (bx + bw + 20) and (by - 10) <= pt.y <= (by + bh + 60):
                    dbg('click_is_send: click is within composer band -> SEND')
                    return True
                dbg('click_is_send: click OUTSIDE composer band -> not a send')
                return False
        except Exception:
            pass
        # Couldn't locate the composer. Only trust a bare clickable control if it lives INSIDE
        # the web page (AXWebArea) -- never browser chrome like Reload, tabs, toolbar, DevTools.
        n, in_page = el, False
        for _ in range(40):
            if n is None:
                break
            role = ax(n, 'AXRole')
            if role in ('AXToolbar', 'AXTabGroup', 'AXMenuBar', 'AXMenu'):
                return False
            if role == 'AXWebArea':
                in_page = True
                break
            n = ax(n, 'AXParent')
        dbg('click_is_send: no composer rect; inside web page =', in_page)
        return clickable is not None and in_page



# ---------------- Native non-activating warning panel ----------------
import objc as _objc
from AppKit import (
    NSPanel, NSView, NSColor, NSFont, NSTextField, NSButton, NSBezierPath,
    NSMakeRect, NSScreen, NSFloatingWindowLevel, NSApp,
    NSBackingStoreBuffered, NSBezelStyleRounded, NSTextAlignmentCenter,
)
from Foundation import NSObject as _NSObj

_NONACT_PANEL = 1 << 7


class _HHPanelWin(NSPanel):
    # A nonactivating floating panel. It may become KEY (so its buttons accept clicks)
    # but never MAIN (which would activate the app and disturb a full-screen Space).
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False
_BORDERLESS = 0


class _HHCard(NSView):
    def initWithFrame_hard_(self, frame, hard):
        self = _objc.super(_HHCard, self).initWithFrame_(frame)
        if self is None:
            return None
        self._hard = hard
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def acceptsFirstResponder(self):
        return True

    def keyDown_(self, event):
        try:
            ch = event.charactersIgnoringModifiers()
            from AppKit import NSEventModifierFlagCommand
            cmd = bool(event.modifierFlags() & NSEventModifierFlagCommand)
            ctrl = getattr(self, '_ctrl', None)
            if ch in ('\r', '\x1b'):          # Return or Esc -> edit (dismiss, stay held)
                if ctrl: ctrl.finish_('edit')
                return
            if cmd and ch in ('\r',) and ctrl and getattr(ctrl, '_allow_send', False):
                ctrl.finish_('send_anyway')
                return
        except Exception:
            pass

    @_objc.python_method
    def _dark(self):
        try:
            n = self.effectiveAppearance().bestMatchFromAppearancesWithNames_(
                ['NSAppearanceNameAqua', 'NSAppearanceNameDarkAqua'])
            return 'Dark' in str(n)
        except Exception:
            return True

    def drawRect_(self, rect):
        b = self.bounds()
        inset = NSMakeRect(b.origin.x + 1, b.origin.y + 1, b.size.width - 2, b.size.height - 2)
        card = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, 18, 18)
        if self._dark():
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.086, 0.094, 0.11, 1.0).set()
        else:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 0.98, 1.0).set()
        card.fill()
        # top accent bar
        if self._hard:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.70, 0.23, 0.20, 1).set()
        else:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.78, 0.63, 0.30, 1).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(inset.origin.x, inset.origin.y, inset.size.width, 5), 2.5, 2.5).fill()
        NSColor.colorWithCalibratedWhite_alpha_(0.5 if self._dark() else 0.15, 0.3).set()
        card.setLineWidth_(1.0)
        card.stroke()


class _HHButton(NSButton):
    def acceptsFirstMouse_(self, event):
        return True


class _HHCtrl(_NSObj):
    def initWithGuard_pid_(self, guard, pid):
        self = _objc.super(_HHCtrl, self).init()
        if self is None:
            return None
        self.guard = guard
        self.pid = pid
        self.window = None
        return self

    def edit_(self, sender):
        self.finish_('edit')

    def sendAnyway_(self, sender):
        self.finish_('send_anyway')

    @_objc.python_method
    def finish_(self, choice):
        if getattr(self, '_done', False):
            return
        self._done = True
        if self.window is not None:
            self.window.orderOut_(None)
            self.window = None
        self.guard.on_panel_choice(choice, {'pid': self.pid})
        HHPanel._active = None

    def autoDismiss_(self, timer):
        if not getattr(self, '_done', False):
            self.finish_('edit')


class HHPanel:
    _active = None

    @staticmethod
    def show(guard, r, hard, p, cls_, asg):
        if HHPanel._active is not None:
            try:
                HHPanel._active.window.orderOut_(None)
            except Exception:
                pass
            HHPanel._active = None

        ctrl = _HHCtrl.alloc().initWithGuard_pid_(guard, p['pid'])
        W, pad = 384.0, 20.0
        reason = r.get('reason') or (r.get('reasons') or ['This looks like it breaks a rule for this class.'])[0]
        header = 'Message blocked' if hard else 'Hold on a second'
        ctx = cls_['name'] + (f' / {asg["name"]}' if asg else '') + '  ·  ' + p['where']
        lines = [('why', reason)]
        if r.get('rule'):
            lines.append(('rule', 'Rule: ' + r['rule']))
        if r.get('quote'):
            lines.append(('quote', '\u201c' + r['quote'] + '\u201d'))
        if r.get('tip'):
            lines.append(('tip', 'Try instead: ' + r['tip']))
        foot = ('Checked by the ' + ('AI judge' if r.get('source') == 'ai' else 'keyword rules') + '.'
                + ('  Press Return to edit.' if hard
                   else '  Return = edit · \u2318Return = send anyway (logged).'))

        scr = NSScreen.mainScreen().frame()
        win = _HHPanelWin.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, 300), _BORDERLESS | _NONACT_PANEL, NSBackingStoreBuffered, False)
        win.setLevel_(NSFloatingWindowLevel)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(True)
        win.setHidesOnDeactivate_(False)
        win.setBecomesKeyOnlyIfNeeded_(True)
        win.setFloatingPanel_(True)
        # Named collection-behavior bits (clearer than raw shifts) so the panel floats
        # OVER full-screen apps and stays clickable in that Space.
        try:
            from AppKit import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorIgnoresCycle,
            )
            win.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorIgnoresCycle)
        except Exception:
            win.setCollectionBehavior_((1 << 0) | (1 << 8))
        win.setWorksWhenModal_(True)

        card = _HHCard.alloc().initWithFrame_hard_(NSMakeRect(0, 0, W, 300), hard)
        win.setContentView_(card)
        dark = card._dark()
        ink = NSColor.whiteColor() if dark else NSColor.colorWithCalibratedWhite_alpha_(0.08, 1)
        muted = NSColor.colorWithCalibratedWhite_alpha_(0.62 if dark else 0.42, 1)
        brass = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.80, 0.66, 0.33, 1)

        def label(text, y0, size, color, bold=False):
            f = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, y0, W - 2 * pad, 20))
            f.setStringValue_(text)
            f.setBezeled_(False); f.setDrawsBackground_(False)
            f.setEditable_(False); f.setSelectable_(False)
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
            f.setTextColor_(color)
            f.cell().setWraps_(True)
            f.setFrameSize_((W - 2 * pad, 2000)); f.sizeToFit()
            fr = f.frame()
            f.setFrame_(NSMakeRect(pad, y0, W - 2 * pad, fr.size.height))
            card.addSubview_(f)
            return y0 + fr.size.height

        yy = pad + 6
        yy = label(header, yy, 17, ink, True) + 2
        yy = label(ctx, yy, 11.5, muted) + 10
        for kind, text in lines:
            col = brass if kind == 'tip' else (muted if kind == 'quote' else ink)
            yy = label(text, yy, 13.5 if kind == 'why' else 12.5, col) + 7
        yy = label(foot, yy + 3, 11, muted) + 14

        bh = 32.0
        def button(title, x0, w, sel, primary):
            btn = _HHButton.alloc().initWithFrame_(NSMakeRect(x0, yy, w, bh))
            btn.setTitle_(title)
            try:
                btn.setBezelStyle_(NSBezelStyleRounded)
            except Exception:
                btn.setBezelStyle_(1)
            btn.setTarget_(ctrl)
            btn.setAction_(sel)
            if primary:
                btn.setKeyEquivalent_('\r')
            card.addSubview_(btn)

        if hard:
            button('OK, I\u2019ll edit it', W - pad - 160, 160, 'edit:', True)
        else:
            button('Edit', pad, 92, 'edit:', True)
            button('Send anyway', W - pad - 150, 150, 'sendAnyway:', False)
        yy += bh + pad

        H = yy
        x = scr.origin.x + scr.size.width - W - 18
        y = scr.origin.y + scr.size.height - H - 40
        win.setFrame_display_(NSMakeRect(x, y, W, H), True)
        card.setFrame_(NSMakeRect(0, 0, W, H))

        card._ctrl = ctrl
        ctrl._allow_send = (not hard)
        ctrl.window = win
        HHPanel._active = ctrl
        win.setInitialFirstResponder_(card)
        # Raise above normal floating so it shows atop full-screen windows, then make it key
        # so its buttons accept the first click without leaving the full-screen Space.
        try:
            from AppKit import NSStatusWindowLevel
            win.setLevel_(NSStatusWindowLevel)
        except Exception:
            pass
        # Proven pattern: order it front WITHOUT activating. becomesKeyOnlyIfNeeded lets
        # macOS hand the panel key focus only when the user actually clicks a control,
        # so buttons work on first click yet the full-screen Space is never disturbed.
        win.orderFrontRegardless()
        try:
            from Foundation import NSTimer
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                25.0, ctrl, 'autoDismiss:', None, False)
        except Exception:
            pass
