#!/usr/bin/env python3
"""Run this (with the venv active) while Gemini is focused with some text typed, to see
what HonestHands can read. Helps debug sites that slip past. Ctrl+C to stop."""
import time
import watcher as w

def main():
    if not w.has_accessibility():
        print("Grant Accessibility first (System Settings > Privacy & Security > Accessibility).")
        return
    print("Focus an AI site/app and type something (don't send). Ctrl+C to stop.\n")
    last = None
    try:
        while True:
            app = w.front_app()
            if app and w.watchable(app):
                w.wake_accessibility(app)
                bid, name, pid = w.app_info(app)
                import ApplicationServices as A
                appel = A.AXUIElementCreateApplication(pid)
                A.AXUIElementSetMessagingTimeout(appel, 0.5)
                focused = w.ax(appel, 'AXFocusedUIElement')
                box = w.find_composer(appel, focused)
                p = w.current_prompt()
                line = (f"app={name}\n  focused role={w.ax(focused,'AXRole')} sub={w.ax(focused,'AXSubrole')}\n"
                        f"  box found={'yes' if box else 'NO'}  role={w.ax(box,'AXRole') if box else '-'}\n"
                        f"  where={p['where'] if p else None}\n  text={repr((p['text'][:80]) if p else None)}")
                if line != last:
                    print(line, "\n"); last = line
            time.sleep(1)
    except KeyboardInterrupt:
        print("stopped")

if __name__ == '__main__':
    main()
