#!/usr/bin/env python3
"""Regression suite for the AI guard.

    python3 tests/run_guard_tests.py                 # use whichever model Settings has selected
    python3 tests/run_guard_tests.py --model small   # or: --model large
    python3 tests/run_guard_tests.py --only hw2-     # only cases whose id starts with this

It runs the REAL guard (real model, real checklist, your saved classes and assignments) on every case in
tests/guard_cases.json and appends the result to tests/results.jsonl, so changes to the model or the prompts
can be compared run to run. Exit code 1 if a case that used to pass now fails, or any non-xfail case fails.
"""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ai_guard                                  # noqa: E402
from engine import Engine, MODELS                # noqa: E402
from store import Store, TUTOR_CLASS             # noqa: E402

CASES = ROOT / 'tests' / 'guard_cases.json'
RESULTS = ROOT / 'tests' / 'results.jsonl'


def git(*a):
    try:
        return subprocess.check_output(['git', *a], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ''


def prompt_fingerprint():
    """Changes whenever any of the guard's instructions change."""
    blob = ''.join(getattr(ai_guard, n) for n in ('SYSTEM', 'EXTRACT_SYSTEM', 'CLASSIFY_SYSTEM', 'VERIFY_SYSTEM', 'RELATED_SYSTEM', 'HOMEWORK_SYSTEM'))
    return hashlib.sha1(blob.encode()).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', choices=list(MODELS), help='model to test (default: the one chosen in Settings)')
    ap.add_argument('--only', default='', help='run only case ids starting with this')
    ap.add_argument('--config', help='read classes from this config.json (e.g. a backup) instead of the live one')
    ap.add_argument('--no-record', action='store_true', help="don't append to results.jsonl")
    args = ap.parse_args()

    if args.config:
        import store as _st
        _st.CONFIG = Path(args.config)
    store = Store()
    if args.model:
        store.data['engine']['model'] = args.model            # in memory only; nothing is saved
    engine = Engine(store)
    engine.autostart()
    t0 = time.time()
    while not engine.ready() and time.time() - t0 < 240:
        time.sleep(0.5)
    if not engine.ready():
        sys.exit(f'The AI never became ready: {engine.message}')
    wanted = MODELS[args.model]['file'] if args.model else None
    if wanted and engine.model()['file'] != wanted:
        sys.exit(f'Asked for the "{args.model}" model but it is not downloaded, so the app would fall back to '
                 f'{engine.model()["file"]}. Download it in Settings first.')
    model_file = engine.model()['file']
    guard = ai_guard.AIGuard(store, engine)

    def find(name):
        if name == TUTOR_CLASS['name']:
            return TUTOR_CLASS
        return next((c for c in store.data['classes'] if c['name'] == name), None)

    cases = [c for c in json.loads(CASES.read_text()) if c['id'].startswith(args.only)]
    prev = {}
    if RESULTS.exists():
        for line in RESULTS.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('model') == model_file:
                prev = r.get('cases', {})
    print(f'model: {model_file} | prompts: {prompt_fingerprint()} | {len(cases)} cases\n')

    rows, skipped = {}, []
    for c in cases:
        cls = find(c['class'])
        asg = next((a for a in (cls or {}).get('assignments', []) if a['name'] == c.get('assignment')), None) if c.get('assignment') else None
        if cls is None or (c.get('assignment') and asg is None):
            skipped.append(c['id']); continue
        r = guard.check(c['message'], cls, asg, 'gemini.google.com', timeout=90, use_cache=False)
        got = 'allow' if r['verdict'] == 'allow' else 'flag'
        rows[c['id']] = {'pass': got == c['expect'], 'got': got, 'expect': c['expect'], 'ms': r['ms'], 'source': r['source'],
                         'xfail': bool(c.get('xfail')), 'reason': r.get('reason', '')}
        mark = 'ok  ' if rows[c['id']]['pass'] else ('xfail' if c.get('xfail') else 'FAIL')
        print(f"{mark:5} {c['id']:24} expect {c['expect']:5} got {got:5} {r['ms']:>5}ms {r['source']:8} | {c['message'][:56]}")

    n = len(rows)
    passed = sum(v['pass'] for v in rows.values())
    hard_fail = [k for k, v in rows.items() if not v['pass'] and not v['xfail']]
    regress = [k for k, v in rows.items() if not v['pass'] and prev.get(k, {}).get('pass')]
    fixed = [k for k, v in rows.items() if v['pass'] and prev.get(k) and not prev[k]['pass']]
    avg = int(sum(v['ms'] for v in rows.values()) / n) if n else 0
    print(f'\n{passed}/{n} as expected | avg {avg} ms | not using the AI: {sum(v["source"] != "ai" for v in rows.values())}')
    if skipped: print('skipped (class/assignment not saved on this Mac):', ', '.join(skipped))
    if fixed: print('newly passing:', ', '.join(fixed))
    if regress: print('REGRESSIONS (passed last run on this model):', ', '.join(regress))

    if not args.no_record and not args.only:
        dirty = bool(git('status', '--porcelain', '--', '*.py'))
        rec = {'t': int(time.time()), 'model': model_file, 'prompts': prompt_fingerprint(),
               'commit': git('rev-parse', '--short', 'HEAD') + ('+local' if dirty else ''),
               'accuracy': round(100 * passed / n) if n else 0, 'passed': passed, 'total': n, 'avg_ms': avg,
               'failed': hard_fail, 'cases': rows}
        with RESULTS.open('a') as f:
            f.write(json.dumps(rec) + '\n')
        print(f'recorded in tests/results.jsonl ({rec["commit"]}, prompts {rec["prompts"]})')
    sys.exit(1 if (hard_fail or regress) else 0)


if __name__ == '__main__':
    main()
