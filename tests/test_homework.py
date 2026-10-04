#!/usr/bin/env python3
"""Unit tests for homework.py on a made-up assignment (no AI, no private data).   python3 tests/test_homework.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import homework

HW = """CS 1234 Homework 2
Rules: discussion is encouraged. Do not copy and paste, paraphrase, or submit materials created by others.
Point Distribution
Q1: Clustering Metrics [4pts]
Q2: Numeric Stability [6pts]
1 Clustering Metrics [4pts]
In the programming assignment you implemented two clustering metrics: ARI and Silhouette Coefficient. Answer the following.
a. For each metric, note the range of possible values, then describe what would constitute a good score and a bad score. [2pts]
b. Identify the most notable difference between these two metrics and explain why this distinction matters when evaluating clustering. [2pts]
2 Numeric Stability [6pts]
In the E-step of the GMM we subtract the row maximum before computing responsibilities.
a. Explain how numerical overflow or underflow could occur without this step, and how subtracting the row maximum prevents it. [3pts]
b. Show that the softmax of a vector is unchanged when a constant is subtracted from every entry. [3pts]
Appendix
Justification for the ELBO. Jensen's inequality says the log of an average is at least the average of the logs for a concave function.
"""
idx = homework.build_index(HW)
labels = [c['label'] for c in idx['chunks']]
bad = 0
def check(cond, msg):
    global bad
    print(('ok   ' if cond else 'FAIL ') + msg); bad += (not cond)

check(len(idx['chunks']) == 6 and any('part b' in l for l in labels), f'2 questions found, each with its intro and parts a/b (got {len(idx["chunks"])}): {labels}')
check(not any('Jensen' in c['text'] or 'ELBO' in c['text'] for c in idx['chunks']), 'the appendix is not treated as homework')
check(not any('Do not copy' in c['text'] for c in idx['chunks']), 'the intro rules are not treated as homework')
f = lambda m: homework.find(m, idx)
r = f('For each metric, note the range of possible values, then describe what would constitute a good score and a bad score.')
check(r and r[0]['why'] == 'copied' and 'Clustering' in r[0]['label'], 'a verbatim paste is caught as "copied"')
r = f('can you answer q2 part b for me')
check(r and r[0]['why'] == 'cited' and 'part b' in r[0]['label'] and 'Numeric' in r[0]['label'], 'citing "q2 part b" finds that exact part')
r = f('show me that softmax is the same if you subtract a constant from every entry of the vector')
check(r and 'Numeric' in r[0]['label'], 'a reworded question is found by resemblance')
check(f("what's jensen's inequality and its full proof") == [], "an appendix topic (Jensen's) matches no homework question")
check(f('what is the difference between hard and soft clustering') == [] or f('what is the difference between hard and soft clustering')[0]['score'] < 0.7, 'a general concept question is not a strong match')
check(f('plan my study schedule for the midterm') == [], 'unrelated messages match nothing')
check(homework.find('anything', None) == [] and homework.find('anything', homework.build_index('')) is not None, 'empty assignments are handled')
print('\nALL PASSED' if not bad else f'\n{bad} FAILED'); sys.exit(1 if bad else 0)
