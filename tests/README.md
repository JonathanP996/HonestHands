# Guard regression tests

`guard_cases.json` is a list of exact messages with the result we expect (`allow` or `flag`) for a given class and
assignment. `run_guard_tests.py` runs the real guard on all of them and appends the outcome to `results.jsonl`.

    source .venv/bin/activate
    python3 tests/run_guard_tests.py                  # the model chosen in Settings
    python3 tests/run_guard_tests.py --model large    # compare another model
    python3 tests/run_guard_tests.py --only hw2-latex # a subset (not recorded)

Run it whenever you change the **model**, the **prompts** (`ai_guard.py`), or the **policy text** of a class.
The summary shows accuracy, speed, newly passing cases and any REGRESSION (a case that passed on the previous run
with the same model). `results.jsonl` is the running history: model, prompt fingerprint, git commit, accuracy.

## Adding a case
When the guard gets something wrong in real use, copy the **exact message** into `guard_cases.json`:

    {"id": "short-name", "class": "Machine Learning", "assignment": "Homework2", "expect": "flag",
     "message": "the exact text you typed", "why": "what went wrong"}

Use `"xfail": true` for a known failure you want to track without failing the run.
Cases use your *saved* classes and assignments (they live on this Mac, not in the repo), so a case is skipped
if its class or assignment isn't saved. `Tutor mode` is built in and always available.
