#!/usr/bin/env python3
"""Pictures attached to a message: generated here (no real homework in the repo), read with Apple Vision, judged by the guard.

    python3 tests/test_images.py [--config path/to/config.json]     (needs the 'Machine Learning' class with 'Homework2' saved)
"""
import argparse, base64, random, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from AppKit import NSImage, NSBitmapImageRep, NSColor, NSFont, NSString, NSMakeRect, NSBezierPath, NSPNGFileType, NSFontAttributeName, NSForegroundColorAttributeName  # noqa: E402
from Foundation import NSDictionary  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument('--config'); args = ap.parse_args()
if args.config:
    import store as _st; _st.CONFIG = Path(args.config)
from store import Store  # noqa: E402
from engine import Engine  # noqa: E402
import ai_guard  # noqa: E402


def picture(lines, size=(1100, 420), font=26, scribbles=False):
    img = NSImage.alloc().initWithSize_(size); img.lockFocus()
    NSColor.whiteColor().set(); NSBezierPath.fillRect_(NSMakeRect(0, 0, *size))
    attrs = NSDictionary.dictionaryWithObjectsAndKeys_(NSFont.systemFontOfSize_(font), NSFontAttributeName, NSColor.blackColor(), NSForegroundColorAttributeName, None)
    y = size[1] - 60
    for ln in lines:
        NSString.stringWithString_(ln).drawAtPoint_withAttributes_((30, y), attrs); y -= font + 16
    if scribbles:
        random.seed(3); NSColor.darkGrayColor().set()
        for _ in range(40):
            p = NSBezierPath.bezierPath(); p.moveToPoint_((random.randint(0, size[0]), random.randint(0, size[1]))); p.lineToPoint_((random.randint(0, size[0]), random.randint(0, size[1]))); p.setLineWidth_(3); p.stroke()
    img.unlockFocus()
    png = bytes(NSBitmapImageRep.alloc().initWithData_(img.TIFFRepresentation()).representationUsingType_properties_(NSPNGFileType, None))
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


Q3A = ["3 Numeric Stability [6pts]",
       "a. In the E-step of the GMM, we subtract the row maximum from the unnormalized model",
       "outputs before computing the responsibilities. Explain how numerical overflow or underflow",
       "could occur if this stabilization step were not performed."]
CASES = [  # (name, text, picture lines, scribbles, expected)
    ('"do this" + screenshot of question 3a',   'do this', Q3A, False, 'flag'),
    ('picture only (screenshot of 3a)',          '', Q3A, False, 'flag'),
    ('"do this" + a photo it cannot read',       'do this', [], True, 'flag'),
    ('"what is this?" + an unrelated caption',   'what is this?', ['My cat Mochi sleeping on the couch in the sun'], False, 'allow'),
]
store = Store(); engine = Engine(store); engine.autostart()
while not engine.ready(): time.sleep(0.5)
guard = ai_guard.AIGuard(store, engine)
cls = next((c for c in store.data['classes'] if c['name'] == 'Machine Learning'), None)
asg = next((a for a in (cls or {}).get('assignments', []) if a['name'] == 'Homework2'), None)
if not asg: sys.exit('Needs the Machine Learning class with Homework2 saved (use --config for a backup).')
guard.items_for(cls, asg, wait=120)
bad = 0
for name, text, lines, scr, exp in CASES:
    r = guard.check_with_images(text, [picture(lines, scribbles=scr)], cls, asg, 'gemini.google.com', timeout=60, use_cache=False)
    got = 'allow' if r['verdict'] == 'allow' else 'flag'; ok = got == exp; bad += (not ok)
    print(f"{'ok  ' if ok else 'FAIL'} expect {exp:5} got {got:5} {r['ms']:>5}ms  {name}" + (f"\n       -> {r['reason'][:150]}" if got == 'flag' else ''))
print('\nALL PASSED' if not bad else f'\n{bad} FAILED'); sys.exit(1 if bad else 0)
