#!/usr/bin/env python3
"""End-to-end test of cloud.py against a tiny in-memory stand-in for Supabase (no network, no real account).

    python3 tests/test_cloud_mock.py

Two people: A and B sign in with an email code, pick handles, A invites B both ways, B accepts, A overrides a warning,
the prompt syncs, and B sees it. Also checks what is NOT uploaded."""
import json, os, re, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = {'pw': {}, 'users': {}, 'profiles': {}, 'partnerships': [], 'events': {}, 'sessions': {}, 'daily': {}, 'codes': {}, 'tokens': {}}


def new_user(email):
    uid = str(uuid.uuid4())
    DB['users'][email] = uid
    DB['profiles'][uid] = {'id': uid, 'handle': None, 'display_name': email.split('@')[0], 'last_seen': None}
    return uid


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def _uid(self):
        return DB['tokens'].get(self.headers.get('Authorization', '').replace('Bearer ', ''))

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or 'null')

    def _issue(self, uid, email):
        a, r = 'acc-' + uuid.uuid4().hex, 'ref-' + uuid.uuid4().hex
        DB['tokens'][a] = uid; DB['tokens'][r] = uid
        return {'access_token': a, 'refresh_token': r, 'expires_in': 3600, 'user': {'id': uid, 'email': email}}

    def do_POST(self): self.route('POST')
    def do_GET(self): self.route('GET')
    def do_PATCH(self): self.route('PATCH')
    def do_DELETE(self): self.route('DELETE')

    def route(self, m):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; p = u.path
        body = self._body() if m in ('POST', 'PATCH') else None
        if p == '/auth/v1/otp':
            DB['codes'][body['email']] = '123456'; return self._send(200, {})
        if p == '/auth/v1/verify':
            if DB['codes'].get(body['email']) != body['token']: return self._send(403, {'error_code': 'otp_expired', 'msg': 'Token has expired or is invalid'})
            uid = DB['users'].get(body['email']) or new_user(body['email'])
            return self._send(200, self._issue(uid, body['email']))
        if p == '/auth/v1/signup':
            if body['email'] in DB['users']: return self._send(200, {'id': str(uuid.uuid4()), 'email': body['email']})   # existing: no session, no error
            uid = new_user(body['email']); DB['pw'][body['email']] = body['password']
            return self._send(200, self._issue(uid, body['email']))
        if p == '/auth/v1/token' and q.get('grant_type') == 'password':
            if DB['pw'].get(body['email']) != body['password'] or body['email'] not in DB['users']:
                return self._send(400, {'error_code': 'invalid_credentials', 'msg': 'Invalid login credentials'})
            return self._send(200, self._issue(DB['users'][body['email']], body['email']))
        if p == '/auth/v1/token':
            uid = DB['tokens'].get(body['refresh_token'])
            return self._send(200, self._issue(uid, 'x')) if uid else self._send(400, {'msg': 'bad refresh'})
        if p == '/auth/v1/logout': return self._send(204, None)
        uid = self._uid()
        if not uid: return self._send(401, {'message': 'no auth'})
        t = p.replace('/rest/v1/', '')
        if t == 'rpc/heartbeat': DB['profiles'][uid]['last_seen'] = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()); return self._send(204, None)
        if t == 'rpc/find_profile':
            return self._send(200, [{'id': x['id'], 'display_name': x['display_name']} for x in DB['profiles'].values() if x['handle'] == body['h'].lower() and x['id'] != uid])
        if t == 'profiles':
            rows = [x for x in DB['profiles'].values() if q.get('id', '').replace('eq.', '') in ('', x['id'])]
            if m == 'PATCH':
                if body.get('handle') and any(x['handle'] == body['handle'] for x in DB['profiles'].values() if x['id'] != uid):
                    return self._send(409, {'code': '23505', 'message': 'duplicate key value'})
                DB['profiles'][uid].update(body); return self._send(204, None)
            return self._send(200, rows)
        def visible(owner): return owner == uid or any(r['subject'] == owner and r['watcher'] == uid and r['status'] == 'active' for r in DB['partnerships'])
        if t == 'partnerships':
            if m == 'POST':
                if any(r['subject'] == body['subject'] and r['watcher'] == body['watcher'] for r in DB['partnerships']): return self._send(409, {'code': '23505', 'message': 'duplicate key'})
                DB['partnerships'].append(dict(body, id=str(uuid.uuid4()), status='pending', created_at='2026-01-01T00:00:00+00:00')); return self._send(201, None)
            if m == 'PATCH':
                pid = q['id'].replace('eq.', '')
                for r in DB['partnerships']:
                    if r['id'] == pid and r['requested_by'] != uid: r['status'] = body['status']
                return self._send(204, None)
            if m == 'DELETE':
                pid = q['id'].replace('eq.', ''); DB['partnerships'] = [r for r in DB['partnerships'] if r['id'] != pid]; return self._send(204, None)
            out = []
            for r in DB['partnerships']:
                if uid in (r['subject'], r['watcher']):
                    out.append(dict(r, subject_p=DB['profiles'][r['subject']], watcher_p=DB['profiles'][r['watcher']]))
            return self._send(200, out)
        if t in ('events', 'sessions', 'daily'):
            store = DB[t]
            if m == 'POST':
                rows = body if isinstance(body, list) else [body]
                for r in rows:
                    assert r['user_id'] == uid, 'row not owned by caller'
                    if t == 'events': assert r.get('kind') == 'overridden', 'only overridden events may be uploaded'
                    key = (r['user_id'], r['day']) if t == 'daily' else r['id']
                    if t == 'events' and key in store: continue
                    store[key] = r
                return self._send(201, None)
            ids = None
            if 'user_id' in q:
                v = q['user_id']; ids = v[4:-1].split(',') if v.startswith('in.(') else [v.replace('eq.', '')]
            rows = [r for r in store.values() if (ids is None or r['user_id'] in ids) and visible(r['user_id'])]
            if t == 'events':
                rows = [dict(r, who=DB['profiles'][r['user_id']]) for r in rows]
            if 'day' in q and q['day'].startswith('gte.'): rows = [r for r in rows if r['day'] >= q['day'][4:]]
            return self._send(200, sorted(rows, key=lambda r: r.get('at') or r.get('started_at') or r.get('day') or '', reverse=True))
        self._send(404, {'message': 'unknown ' + p})


srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ['HH_SUPABASE_URL'] = f'http://127.0.0.1:{srv.server_address[1]}'
import cloud   # noqa: E402  (reads the URL at import)


class FakeStore:
    def __init__(self, log): self.data = {'cloud': {}}; self._log = log
    def save(self): pass
    def read_log(self, limit=None): return list(self._log)


T0 = time.time() - 600


class FakeApp:
    class api:
        @staticmethod
        def sessions(n):
            t = T0
            return [{'class': 'Machine Learning', 'assignment': 'Homework2', 'start': t, 'end': t + 500, 'seconds': 500}]


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond: check.bad += 1
check.bad = 0

now = time.time()
log_a = [{'t': now - 300, 'where': 'gemini.google.com', 'class': 'Machine Learning', 'assignment': 'Homework2', 'text': 'convert this problem 1a into latex', 'result': 'warned',
          'reasons': ['This asks the AI to fix or format LaTeX.', 'Rule: use AI to fix or format LaTeX']},
         {'t': now - 290, 'where': 'gemini.google.com', 'class': 'Machine Learning', 'assignment': 'Homework2', 'text': 'convert this problem 1a into latex', 'result': 'sent anyway'},
         {'t': now - 200, 'where': 'gemini.google.com', 'class': 'Machine Learning', 'assignment': 'Homework2', 'text': 'my private clean question about my diary', 'result': 'ok'}]
A = cloud.Cloud(FakeStore(log_a), FakeApp()); B = cloud.Cloud(FakeStore([]), FakeApp())

try: A.sign_up('dana@school.edu', 'short'); check(False, 'rejects a short password')
except cloud.CloudError: check(True, 'password sign-up rejects a short password')
D = cloud.Cloud(FakeStore([]), FakeApp()); r = D.sign_up('dana@school.edu', 'correct horse battery'); check(D.signed_in and r['needs_confirm'] is False, 'password sign-up signs you straight in')
D.sign_out(); check(not D.signed_in, 'sign out works for password accounts')
try: D.sign_in('dana@school.edu', 'wrong password'); check(False, 'wrong password')
except cloud.CloudError as e: check('Wrong email or password' in str(e), 'a wrong password gets a friendly message')
check(D.sign_in('dana@school.edu', 'correct horse battery')['id'], 'password sign-in works')
check(D.sign_up('dana@school.edu', 'another password 1')['needs_confirm'] is True, 'signing up with an existing email does not sign you in')
try: A.send_code('nope'); check(False, 'rejects a bad email')
except cloud.CloudError: check(True, 'rejects a bad email')
A.send_code('alice@school.edu')
try: A.verify('alice@school.edu', '000000'); check(False, 'rejects a wrong code')
except cloud.CloudError as e: check('wrong or expired' in str(e), 'rejects a wrong code with a friendly message')
me = A.verify('alice@school.edu', '123456'); check(A.signed_in and me['handle'] is None, 'A signs in with the emailed code (no handle yet)')
B.send_code('bob@school.edu'); B.verify('bob@school.edu', '123456')
try: A.set_profile('x', 'Alice'); check(False, 'rejects a short handle')
except cloud.CloudError: check(True, 'rejects a short handle')
check(A.set_profile('Alice_K', 'Alice')['handle'] == 'alice_k', 'A picks a handle (lower-cased)')
try: B.set_profile('alice_k', 'Bob'); check(False, 'handles are unique')
except cloud.CloudError as e: check('taken' in str(e), 'a duplicate handle is refused politely')
B.set_profile('bobby', 'Bob')
try: A.invite('nobody_here', 'both'); check(False, 'unknown handle')
except cloud.CloudError as e: check('No one has' in str(e), 'inviting an unknown handle explains itself')
r = A.invite('@bobby', 'both'); check(r['sent'] == 2, 'A invites Bob both ways (2 links)')
try: A.invite('bobby', 'both'); check(False, 'duplicate invite')
except cloud.CloudError: check(True, 'a repeat invite is refused')
ovb = B.overview(); check(len(ovb['requests']) == 2, 'Bob sees 2 requests waiting')
for rq in ovb['requests']: B.respond(rq['id'], True)
ova = A.overview(); check(len(ova['watching']) == 1 and len(ova['watchers']) == 1 and ova['watching'][0]['mutual'], 'A and B are mutual partners')

A.sync_now()
ev = list(DB['events'].values()); check(len(ev) == 1, 'exactly one prompt was uploaded (the override)')
check(ev and ev[0]['prompt_text'] == 'convert this problem 1a into latex' and ev[0]['reason'] and ev[0]['rule'], 'it carries the text, the reason and the rule from the warning before it')
check('my private clean question about my diary' not in json.dumps({k: list(v.values()) if isinstance(v, dict) else v for k, v in DB.items()}, default=str), 'the text of clean messages never left the Mac')
sess = list(DB['sessions'].values()); check(len(sess) == 1 and sess[0]['overridden'] == 1 and sess[0]['clean'] == 1 and 'prompt_text' not in sess[0], 'the session is uploaded as counts only')
A.sync_now(); check(len(DB['events']) == 1 and len(DB['sessions']) == 1, 'syncing again does not duplicate anything')
A.c['sharing'] = False; A.store._log.append({'t': time.time(), 'where': 'g', 'class': 'c', 'text': 'second override', 'result': 'sent anyway'}); A.sync_now()
check(len(DB['events']) == 1, 'with sharing off, nothing new is uploaded')
A.set_sharing(True); A.sync_now(); check(len(DB['events']) == 2, 'turning sharing back on uploads what was held back')

ovb = B.overview(); check(len(ovb['feed']) == 2 and ovb['feed'][0]['who']['display_name'] == 'Alice', 'Bob\'s feed shows Alice\'s overridden prompts')
fr = B.friend(ovb['watching'][0]['person']['id']); check(fr['totals']['overridden'] >= 1 and len(fr['events']) == 2 and fr['streak'] >= 1, 'Bob can open Alice\'s profile (streak, totals, prompts)')
C = cloud.Cloud(FakeStore([]), FakeApp()); C.send_code('carol@school.edu'); C.verify('carol@school.edu', '123456'); C.set_profile('carol', 'Carol')
check(C.overview()['feed'] == [], 'a stranger sees no feed')
B.end(ovb['watching'][0]['id']); check(len(B.overview()['watching']) == 0, 'Bob can end the connection')
A.sign_out(); check(not A.signed_in, 'signing out clears the session')
print('\nALL PASSED' if not check.bad else f'\n{check.bad} FAILED'); sys.exit(1 if check.bad else 0)
