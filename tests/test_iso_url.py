"""Timestamps that go into a URL filter must not contain '+': it becomes a space and the database rejects the query.
That silently broke 'a friend released you' (the release check never matched)."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import cloud

t = time.time()
s = cloud.iso(t)
assert '+' not in s and s.endswith('Z'), s
assert abs(cloud.from_iso(s) - t) < 0.001
print('ALL PASSED')
