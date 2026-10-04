#!/usr/bin/env python3
"""HonestHands profile scanner.

Run this, then visit each AI website one at a time. For each site:
  1. Click into the message box and type a few words (DON'T send).
  2. Move your mouse over the SEND button and leave it there.

The scanner prints a block for each site describing exactly what HonestHands can
see — the composer and the send button. Copy ALL the output and send it back, and
those readouts become per-site profiles.

Ctrl+C to stop.
"""
import time
import watcher as w
import ApplicationServices as A


def attrs(el, names):
    out = {}
    for n in names:
        v = w.ax(el, n)
        if v is None:
            continue
        s = str(v)
        if s and s != '(null)':
            out[n] = s[:80]
    return out


def describe(el):
    if el is None:
        return "    (none)"
    got = attrs(el, ['AXRole', 'AXSubrole', 'AXRoleDescription', 'AXDescription',
                     'AXTitle', 'AXHelp', 'AXIdentifier', 'AXPlaceholderValue', 'AXValue'])
    return '\n'.join(f"      {k} = {v!r}" for k, v in got.items()) or "      (no readable attributes)"


def button_under_mouse(appel):
    """What's under the mouse right now, climbing to the nearest button-ish control."""
    from Quartz import CGEventCreate, CGEventGetLocation
    ev = CGEventCreate(None)
    pt = CGEventGetLocation(ev)
    sysel = A.AXUIElementCreateSystemWide()
    A.AXUIElementSetMessagingTimeout(sysel, 0.3)
    err, el = A.AXUIElementCopyElementAtPosition(sysel, pt.x, pt.y, None)
    if err != 0 or el is None:
        return None, pt
    node = el
    for _ in range(6):
        if node is None:
            break
        role = w.ax(node, 'AXRole')
        if role in ('AXButton', 'AXLink', 'AXMenuButton', 'AXPopUpButton'):
            return node, pt
        node = w.ax(node, 'AXParent')
    return el, pt  # whatever is under the cursor, even if not a button


def main():
    if not w.has_accessibility():
        print("Grant Accessibility first (System Settings > Privacy & Security > Accessibility), then rerun.")
        return
    print(__doc__)
    print("=" * 66)
    last_key = None
    try:
        while True:
            app = w.front_app()
            if not app or not w.watchable(app):
                time.sleep(0.6)
                continue
            bid, name, pid = w.app_info(app)
            w.wake_accessibility(app)
            appel = A.AXUIElementCreateApplication(pid)
            A.AXUIElementSetMessagingTimeout(appel, 0.5)
            focused = w.ax(appel, 'AXFocusedUIElement')
            box = w.find_profiled_composer(appel, (w.current_prompt() or {}).get('where','')) or w.find_composer(appel, focused)
            p = w.current_prompt()
            where = p['where'] if p else None
            if where is None:
                time.sleep(0.6)
                continue

            btn, pt = button_under_mouse(appel)
            # Only reprint when the site or the composer text changes, to reduce spam.
            key = (where, (p['text'][:20] if p else ''))
            if key == last_key:
                time.sleep(0.6)
                continue
            last_key = key

            print(f"\n### SITE: {where}    (app: {name}, {bid})")
            print("  COMPOSER (where you type):")
            print(describe(box))
            print(f"    -> text read: {repr(p['text'][:80]) if p else None}")
            print("  UNDER MOUSE (hover your SEND button here):")
            print(describe(btn))
            print("  " + "-" * 60)
            time.sleep(0.6)
    except KeyboardInterrupt:
        print("\nStopped. Copy everything above and send it back.")


if __name__ == '__main__':
    main()
