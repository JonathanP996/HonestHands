"""HonestHands cloud: sign-in, partners, and background sync to Supabase. Standard library only.

Privacy rules (see cloud/schema.sql, which the database also enforces):
  - only OVERRIDDEN prompts are uploaded with their text
  - flagged / clean messages are uploaded as counts only (sessions + daily)
  - syllabi and assignment text never leave this Mac
The local log stays the source of truth: sync just re-sends whatever the cloud hasn't got, so being offline loses nothing.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

# Both are PUBLIC by design: the anon key can only do what the row-level security rules in schema.sql allow.
URL = os.environ.get('HH_SUPABASE_URL', 'https://ssndcrmonmtonebbxwok.supabase.co').rstrip('/')
ANON = os.environ.get('HH_SUPABASE_ANON', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNzbmRjcm1vbm10b25lYmJ4d29rIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTExNDk5NjIsImV4cCI6MjEwNjcyNTk2Mn0.VT6AxeMdGROvaVmf3Ww9CJ7adk0M7ufo3MkateEQ4mk')
NS = uuid.UUID('7d9a1c52-3b1e-4f0a-9a57-0f2d6a4b8c11')     # makes row ids reproducible, so re-sending never duplicates
OVERRIDDEN = ('sent anyway', 'sent after warning')
PROFILE_COLS = 'id,handle,display_name,last_seen'


class CloudError(Exception):
    pass


def code_is_429(pgc):
    return str(pgc) == '429'


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def from_iso(s):
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0.0


class Cloud:
    def __init__(self, store, app=None):
        self.store, self.app = store, app
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.status = {'state': 'idle', 'message': '', 'last_sync': 0}
        self._sent_sessions = {}
        self._started = False

    # ------------------------------------------------------------------ state
    @property
    def c(self):
        return self.store.data.setdefault('cloud', {})

    @property
    def signed_in(self):
        return bool(self.c.get('refresh') and self.c.get('user_id'))

    @property
    def uid(self):
        return self.c.get('user_id')

    def _save(self):
        self.store.save()

    # ------------------------------------------------------------------- http
    def _http(self, method, path, body=None, token=None, headers=None, timeout=20):
        h = {'apikey': ANON, 'Authorization': 'Bearer ' + (token or ANON), 'Content-Type': 'application/json'}
        h.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(URL + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode() or 'null'
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {'message': raw[:200]}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise CloudError("Can't reach the cloud. Check your internet connection.") from e

    @staticmethod
    def _friendly(code, payload):
        msg = str((payload or {}).get('message') or (payload or {}).get('msg') or (payload or {}).get('error_description')
                  or (payload or {}).get('error') or payload)
        pgc = str((payload or {}).get('code') or (payload or {}).get('error_code') or '')
        if pgc == 'PGRST205' or 'schema cache' in msg:
            return 'The cloud database isn\'t set up yet. Run cloud/schema.sql in Supabase (SQL Editor), then try again.'
        if pgc == '23505' or 'duplicate key' in msg:
            return 'That already exists.'
        if 'over_email_send_rate_limit' in pgc or 'rate limit' in msg.lower():
            return 'Too many emails right now. Wait a few minutes, then try again.'
        if pgc == 'invalid_credentials' or 'invalid login credentials' in msg.lower():
            return 'Wrong email or password.'
        if pgc == 'email_not_confirmed' or 'not confirmed' in msg.lower():
            return 'Confirm your email first: click the link Supabase emailed you (the page it opens may say "can\'t be reached"; that\'s fine, it still confirms you). Then sign in.'
        if pgc in ('weak_password',) or 'password should be' in msg.lower():
            return 'Choose a longer password (at least 8 characters).'
        if pgc == 'user_already_exists' or 'already registered' in msg.lower():
            return 'That email already has an account. Sign in instead.'
        if pgc == 'over_request_rate_limit' or code_is_429(pgc):
            return 'Too many tries. Wait a minute, then try again.'
        if 'otp_expired' in pgc or 'expired' in msg.lower() or 'invalid' in msg.lower() and 'token' in msg.lower():
            return 'That code is wrong or expired. Ask for a new one.'
        return msg

    def _token(self):
        """A valid access token, refreshing it when it is about to expire."""
        with self.lock:
            if time.time() < self.c.get('expires_at', 0) - 60 and self.c.get('access'):
                return self.c['access']
            if not self.c.get('refresh'):
                raise CloudError('Sign in to use the community.')
            code, p = self._http('POST', '/auth/v1/token?grant_type=refresh_token', {'refresh_token': self.c['refresh']})
            if code != 200:
                self.c.update(access='', refresh='', expires_at=0)       # signed out remotely or token revoked
                self._save()
                raise CloudError('You were signed out. Sign in again.')
            self._adopt(p)
            return self.c['access']

    def _adopt(self, p):
        self.c.update(access=p['access_token'], refresh=p['refresh_token'],
                      expires_at=p.get('expires_at') or time.time() + p.get('expires_in', 3600),
                      user_id=(p.get('user') or {}).get('id') or self.c.get('user_id'),
                      email=(p.get('user') or {}).get('email') or self.c.get('email'))
        self._save()

    def _rest(self, method, path, body=None, prefer=None, ok=(200, 201, 204)):
        h = {'Prefer': prefer} if prefer else {}
        code, p = self._http(method, '/rest/v1/' + path, body, token=self._token(), headers=h)
        if code not in ok:
            raise CloudError(self._friendly(code, p))
        return p

    # ------------------------------------------------------------------- auth
    def send_code(self, email):
        email = (email or '').strip().lower()
        if '@' not in email:
            raise CloudError('Enter a valid email address.')
        code, p = self._http('POST', '/auth/v1/otp', {'email': email, 'create_user': True})
        if code not in (200, 204):
            raise CloudError(self._friendly(code, p))
        return True

    def verify(self, email, token):
        email, token = (email or '').strip().lower(), (token or '').strip().replace(' ', '')
        code, p = self._http('POST', '/auth/v1/verify', {'type': 'email', 'email': email, 'token': token})
        if code != 200 or 'access_token' not in p:
            raise CloudError(self._friendly(code, p))
        with self.lock:
            self._adopt(p)
            self.c.setdefault('sharing', True)
            self.c.setdefault('last_event_t', 0)
            self.c['last_notified_t'] = time.time()
            self._save()
        self.kick()
        return self.me()

    def _start_session(self, p):
        with self.lock:
            self._adopt(p)
            self.c.setdefault('sharing', True)
            self.c.setdefault('last_event_t', 0)
            self.c['last_notified_t'] = time.time()
            self._save()
        self.kick()
        return self.me()

    def sign_up(self, email, password):
        """Create an account. If the project requires email confirmation there is no session yet."""
        email = (email or '').strip().lower()
        if '@' not in email:
            raise CloudError('Enter a valid email address.')
        if len(password or '') < 8:
            raise CloudError('Choose a password with at least 8 characters.')
        code, p = self._http('POST', '/auth/v1/signup', {'email': email, 'password': password})
        if code not in (200, 201):
            raise CloudError(self._friendly(code, p))
        if isinstance(p, dict) and p.get('access_token'):
            return dict(self._start_session(p), needs_confirm=False)
        return {'needs_confirm': True}

    def sign_in(self, email, password):
        email = (email or '').strip().lower()
        code, p = self._http('POST', '/auth/v1/token?grant_type=password', {'email': email, 'password': password or ''})
        if code != 200 or 'access_token' not in p:
            raise CloudError(self._friendly(code, p))
        return self._start_session(p)

    def sign_out(self):
        try:
            if self.c.get('access'):
                self._http('POST', '/auth/v1/logout', token=self.c['access'])
        except CloudError:
            pass
        with self.lock:
            sharing = self.c.get('sharing', True)
            self.store.data['cloud'] = {'sharing': sharing}
            self._save()
        self._sent_sessions.clear()

    # ---------------------------------------------------------------- profile
    def me(self):
        rows = self._rest('GET', f'profiles?id=eq.{self.uid}&select={PROFILE_COLS}')
        p = rows[0] if rows else {'id': self.uid, 'handle': None, 'display_name': (self.c.get('email') or '').split('@')[0]}
        if p.get('handle') and self.c.get('display_name') != p.get('display_name'):
            self.c['display_name'] = p.get('display_name')       # so the sidebar can greet you without a network call
            self._save()
        return {'id': p['id'], 'handle': p.get('handle'), 'display_name': p.get('display_name'), 'email': self.c.get('email'),
                'sharing': bool(self.c.get('sharing', True))}

    def set_profile(self, handle, display_name):
        handle = (handle or '').strip().lower().lstrip('@')
        name = (display_name or '').strip()
        if not (3 <= len(handle) <= 24) or not all(ch.isalnum() and ch.isascii() or ch == '_' for ch in handle):
            raise CloudError('Handles are 3 to 24 letters, numbers or underscores.')
        if not name:
            raise CloudError('Add the name your friends will see.')
        try:
            self._rest('PATCH', f'profiles?id=eq.{self.uid}', {'handle': handle, 'display_name': name[:40]}, prefer='return=minimal')
        except CloudError as e:
            if 'already exists' in str(e):
                raise CloudError('That handle is taken. Try another.')
            raise
        return self.me()

    def set_sharing(self, on):
        self.c['sharing'] = bool(on)
        self._save()
        if on:
            self.kick()
        return self.me()

    # --------------------------------------------------------------- partners
    def invite(self, handle, mode):
        handle = (handle or '').strip().lower().lstrip('@')
        found = self._rest('POST', 'rpc/find_profile', {'h': handle}, ok=(200,))
        if not found:
            raise CloudError(f'No one has the handle @{handle}. Check the spelling.')
        other = found[0]['id']
        rows = []
        if mode in ('watch_me', 'both'):          # they can see me
            rows.append({'subject': self.uid, 'watcher': other, 'requested_by': self.uid})
        if mode in ('watch_them', 'both'):        # I can see them
            rows.append({'subject': other, 'watcher': self.uid, 'requested_by': self.uid})
        if not rows:
            raise CloudError('Choose who can see whom.')
        sent = 0
        for r in rows:                            # one at a time so an existing link doesn't block the other
            try:
                self._rest('POST', 'partnerships', r, prefer='return=minimal')
                sent += 1
            except CloudError as e:
                if 'already exists' not in str(e):
                    raise
        if not sent:
            raise CloudError('You already have that connection with them.')
        return {'sent': sent, 'name': found[0]['display_name']}

    def respond(self, pid, accept):
        if accept:
            self._rest('PATCH', f'partnerships?id=eq.{pid}', {'status': 'active'}, prefer='return=minimal')
        else:
            self._rest('PATCH', f'partnerships?id=eq.{pid}', {'status': 'declined'}, prefer='return=minimal')
        return True

    def end(self, pid):
        self._rest('DELETE', f'partnerships?id=eq.{pid}', prefer='return=minimal')
        return True

    # --------------------------------------------------------------- overview
    def overview(self):
        me = self.me()
        sel = ('select=id,subject,watcher,requested_by,status,created_at,'
               f'subject_p:profiles!partnerships_subject_fkey({PROFILE_COLS}),'
               f'watcher_p:profiles!partnerships_watcher_fkey({PROFILE_COLS})')
        rows = self._rest('GET', f'partnerships?{sel}&order=created_at.desc')
        uid = self.uid
        watching, watchers, requests, outgoing = [], [], [], []
        for r in rows:
            if r['status'] not in ('pending', 'active'):
                continue
            mine_subject = r['subject'] == uid
            person = r['watcher_p'] if mine_subject else r['subject_p']
            item = {'id': r['id'], 'status': r['status'], 'person': person or {'id': '', 'display_name': 'Someone', 'handle': ''},
                    'direction': 'watching_me' if mine_subject else 'i_watch', 'requested_by_me': r['requested_by'] == uid}
            if r['status'] == 'pending':
                (outgoing if item['requested_by_me'] else requests).append(item)
            elif mine_subject:
                watchers.append(item)
            else:
                watching.append(item)
        ids_w = {w['person']['id'] for w in watching}
        mutual = {x['person']['id'] for x in watchers} & ids_w
        for w in watching:
            w['mutual'] = w['person']['id'] in mutual
        for x in watchers:
            x['mutual'] = x['person']['id'] in mutual
        # weekly numbers + latest overrides for the people I watch
        feed, week = [], {}
        if ids_w:
            lst = ','.join(ids_w)
            since = (datetime.now() - timedelta(days=7)).date().isoformat()
            for d in self._rest('GET', f'daily?user_id=in.({lst})&day=gte.{since}&select=*'):
                w = week.setdefault(d['user_id'], {'seconds': 0, 'overridden': 0, 'flagged': 0, 'clean': 0, 'days': 0, 'today_seconds': 0})
                w['seconds'] += d['seconds']; w['overridden'] += d['overridden']; w['flagged'] += d['flagged']; w['clean'] += d['clean']
                w['days'] += 1 if d['sessions'] else 0
                if d['day'] == datetime.now().date().isoformat():
                    w['today_seconds'] = d['seconds']
            feed = self._rest('GET', f'events?user_id=in.({lst})&select=*,who:profiles!events_user_id_fkey({PROFILE_COLS})&order=at.desc&limit=40')
        for w in watching:
            w['week'] = week.get(w['person']['id'], {'seconds': 0, 'overridden': 0, 'flagged': 0, 'clean': 0, 'days': 0, 'today_seconds': 0})
        return {'me': me, 'watching': watching, 'watchers': watchers, 'requests': requests, 'outgoing': outgoing,
                'feed': feed, 'status': self.status, 'server_time': time.time()}

    def friend(self, user_id):
        """Everything a watcher may see about one person (the database enforces who that is)."""
        since = (datetime.now() - timedelta(days=60)).date().isoformat()
        prof = self._rest('GET', f'profiles?id=eq.{user_id}&select={PROFILE_COLS}')
        daily = self._rest('GET', f'daily?user_id=eq.{user_id}&day=gte.{since}&select=*&order=day.asc')
        sessions = self._rest('GET', f'sessions?user_id=eq.{user_id}&select=*&order=started_at.desc&limit=12')
        events = self._rest('GET', f'events?user_id=eq.{user_id}&select=*&order=at.desc&limit=25')
        days = {d['day'] for d in daily if d['sessions']}
        today = datetime.now().date()
        cur, probe = 0, today if today.isoformat() in days else today - timedelta(days=1)
        while probe.isoformat() in days:
            cur += 1; probe -= timedelta(days=1)
        return {'profile': prof[0] if prof else {}, 'daily': daily, 'sessions': sessions, 'events': events, 'streak': cur,
                'totals': {k: sum(d[k] for d in daily) for k in ('seconds', 'sessions', 'clean', 'flagged', 'overridden')}}

    # ------------------------------------------------------------------- sync
    def kick(self):
        self.wake.set()

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        last_sync = last_inbox = last_beat = 0
        self.wake.set()                                  # first pass right away
        while True:
            self.wake.wait(timeout=4)
            woken = self.wake.is_set()
            self.wake.clear()
            if not self.signed_in:
                self.status = {'state': 'signed_out', 'message': '', 'last_sync': 0}
                continue
            now = time.time()
            try:
                if woken or now - last_sync >= 45:
                    last_sync = now
                    self.sync_now()
                    if now - last_beat > 240:
                        self._rest('POST', 'rpc/heartbeat', {}, ok=(200, 204))
                        last_beat = now
                    self._notify_new_overrides()
                    self.status = {'state': 'ok', 'message': '', 'last_sync': time.time()}
                if woken or now - last_inbox >= 12:
                    last_inbox = now
                    self._refresh_inbox()
                if self._locked():
                    self._check_release()                # a friend may have released us: look every few seconds
            except CloudError as e:
                self.status = {'state': 'offline' if "reach" in str(e) else 'error', 'message': str(e), 'last_sync': self.status.get('last_sync', 0)}
            except Exception as e:                       # never let sync take the app down
                self.status = {'state': 'error', 'message': str(e), 'last_sync': self.status.get('last_sync', 0)}

    def _locked(self):
        try:
            return bool(self.app and self.app.locked_now())
        except Exception:
            return False

    # ------------------------------------------------- inbox: messages + release requests
    inbox = {'unread': 0, 'requests': 0}
    watchers_n = None

    def _refresh_inbox(self):
        uid = self.uid
        unread = self._rest('GET', f'messages?to_user=eq.{uid}&read_at=is.null&select=id,body,created_at,sender:profiles!messages_from_user_fkey(display_name)&order=created_at.desc&limit=50')
        pending = self._rest('GET', f'unlock_requests?watcher=eq.{uid}&status=eq.pending&select=id,created_at,who:profiles!unlock_requests_subject_fkey(display_name)&order=created_at.desc')
        self.watchers_n = len(self._rest('GET', f'partnerships?subject=eq.{uid}&status=eq.active&select=id'))
        self.inbox = {'unread': len(unread), 'requests': len(pending)}
        first = not hasattr(self, '_seen_ids')
        if first:
            self._seen_ids = set()
        try:
            import watcher
        except Exception:
            watcher = None
        for m in unread:
            if m['id'] not in self._seen_ids and not first and watcher:
                watcher.notify('HonestHands', f"{(m.get('sender') or {}).get('display_name') or 'A friend'}: {m['body'][:90]}")
            self._seen_ids.add(m['id'])
        for r in pending:
            if r['id'] not in self._seen_ids and not first and watcher:
                watcher.notify('HonestHands', f"{(r.get('who') or {}).get('display_name') or 'A friend'} is asking you to release them from a locked-in session")
            self._seen_ids.add(r['id'])

    def exit_paths(self):
        """How a timed lock-in can be ended early: the PIN, or friends who can release you."""
        return {'pin': bool(self.store.data.get('pin')), 'friends': int(self.watchers_n or 0)}

    # ------------------------------------------------- messages
    def connected(self):
        """People you're connected to (active partnership, either direction), as {id, display_name, handle}."""
        sel = f'select=subject,watcher,subject_p:profiles!partnerships_subject_fkey({PROFILE_COLS}),watcher_p:profiles!partnerships_watcher_fkey({PROFILE_COLS})'
        out = {}
        for r in self._rest('GET', f'partnerships?status=eq.active&{sel}'):
            p = r['watcher_p'] if r['subject'] == self.uid else r['subject_p']
            if p:
                out[p['id']] = p
        return list(out.values())

    def conversations(self):
        uid = self.uid
        msgs = self._rest('GET', f'messages?or=(from_user.eq.{uid},to_user.eq.{uid})&select=*&order=created_at.desc&limit=300')
        rows = []
        for p in self.connected():
            mine = [m for m in msgs if p['id'] in (m['from_user'], m['to_user'])]
            rows.append({'person': p, 'last': mine[0] if mine else None,
                         'unread': sum(1 for m in mine if m['to_user'] == uid and not m.get('read_at'))})
        rows.sort(key=lambda r: (r['last'] or {}).get('created_at', ''), reverse=True)
        return rows

    def thread(self, other):
        uid = self.uid
        flt = f'or=(and(from_user.eq.{uid},to_user.eq.{other}),and(from_user.eq.{other},to_user.eq.{uid}))'
        rows = self._rest('GET', f'messages?{flt}&select=*&order=created_at.asc&limit=200')
        if any(m['to_user'] == uid and not m.get('read_at') for m in rows):
            self._rest('PATCH', f'messages?to_user=eq.{uid}&from_user=eq.{other}&read_at=is.null', {'read_at': iso(time.time())}, prefer='return=minimal')
        return {'messages': rows, 'me': uid}

    def send_message(self, other, body):
        body = (body or '').strip()
        if not body:
            raise CloudError('Type a message first.')
        self._rest('POST', 'messages', {'from_user': self.uid, 'to_user': other, 'body': body[:2000]}, prefer='return=minimal')
        return True

    # ------------------------------------------------- release requests
    def releasers(self):
        """Friends who can release you (they actively watch you)."""
        sel = f'select=id,watcher,watcher_p:profiles!partnerships_watcher_fkey({PROFILE_COLS})'
        rows = self._rest('GET', f'partnerships?subject=eq.{self.uid}&status=eq.active&{sel}')
        self.watchers_n = len(rows)
        return [r['watcher_p'] for r in rows if r.get('watcher_p')]

    def request_unlock(self, note='', watcher_ids=None, class_label='', minutes_left=0):
        allowed = {p['id'] for p in self.releasers()}
        chosen = [w for w in (watcher_ids or list(allowed)) if w in allowed]
        if not chosen:
            raise CloudError('No friend can release you yet. Invite someone with "They can see me" in Community.')
        rows = [{'subject': self.uid, 'watcher': w, 'note': (note or '').strip()[:500] or None, 'class_label': class_label or None,
                 'minutes_left': int(minutes_left or 0)} for w in chosen]
        self._rest('POST', 'unlock_requests', rows, prefer='return=minimal')
        return {'sent': len(chosen)}

    def unlock_status(self, since):
        """The release requests you've made since `since` (a timestamp), with who they went to and what happened."""
        sel = 'select=*,w:profiles!unlock_requests_watcher_fkey(display_name)'
        return self._rest('GET', f'unlock_requests?subject=eq.{self.uid}&created_at=gte.{iso(since)}&{sel}&order=created_at.desc')

    def cancel_unlock(self, rid):
        self._rest('PATCH', f'unlock_requests?id=eq.{rid}&status=eq.pending', {'status': 'cancelled'}, prefer='return=minimal')
        return True

    def incoming_unlocks(self):
        sel = 'select=*,who:profiles!unlock_requests_subject_fkey(id,display_name,handle)'
        return self._rest('GET', f'unlock_requests?watcher=eq.{self.uid}&status=eq.pending&{sel}&order=created_at.desc')

    def decide_unlock(self, rid, approve):
        self._rest('PATCH', f'unlock_requests?id=eq.{rid}&status=eq.pending', {'status': 'approved' if approve else 'denied'}, prefer='return=minimal')
        self.kick()
        return True

    def _check_release(self):
        """While locked in: has a friend approved a request made during THIS session? Then we're released."""
        sess = self.store.data.get('session') or {}
        started = sess.get('started') or 0
        rows = self._rest('GET', f'unlock_requests?subject=eq.{self.uid}&status=eq.approved&created_at=gte.{iso(started)}'
                                 f'&select=id,w:profiles!unlock_requests_watcher_fkey(display_name)&limit=1')
        if rows:
            name = (rows[0].get('w') or {}).get('display_name') or 'A friend'
            self.app.release_session(f'{name} released you')

    def _eid(self, t, text):
        return str(uuid.uuid5(NS, f'{self.uid}|{t:.3f}|{hashlib.sha1((text or "").encode()).hexdigest()}'))

    def _sid(self, start):
        return str(uuid.uuid5(NS, f'{self.uid}|session|{start:.3f}'))

    def build_events(self, entries, since_t):
        """Overridden prompts newer than since_t, with the reason from the warning that came right before them."""
        out = []
        for i, e in enumerate(entries):
            if e.get('result') not in OVERRIDDEN or e['t'] <= since_t:
                continue
            warn = next((w for w in reversed(entries[:i]) if w.get('result') in ('warned', 'blocked')
                         and w.get('text') == e.get('text') and 0 <= e['t'] - w['t'] < 180), None)
            reasons = (warn or {}).get('reasons') or []
            out.append({'id': self._eid(e['t'], e.get('text')), 'user_id': self.uid, 'kind': 'overridden', 'at': iso(e['t']),
                        'site': e.get('where'), 'class_label': e.get('class'), 'assignment_label': e.get('assignment') or None,
                        'prompt_text': (e.get('text') or '')[:2000],
                        'reason': (reasons[0] if reasons else None), 'rule': next((r[6:] for r in reasons if r.startswith('Rule: ')), None)})
        return out

    def sync_now(self):
        if not self.signed_in or not self.c.get('sharing', True):
            return
        import bridge                                   # local import: bridge imports a lot
        entries = self.store.read_log()
        # 1) overridden prompts (the only thing uploaded with text)
        ev = self.build_events(entries, self.c.get('last_event_t', 0))
        if ev:
            self._rest('POST', 'events?on_conflict=id', ev, prefer='resolution=ignore-duplicates,return=minimal')
            self.c['last_event_t'] = max(e['t'] for e in entries if e.get('result') in OVERRIDDEN)
            self._save()
        # 2) sessions: counts only
        msgs = [e for e in entries if 'result' in e]
        sessions = self.app.api.sessions(300) if self.app else []
        rows = []
        for s in sessions[:300]:
            tl = bridge.tally([m for m in msgs if s['start'] <= m['t'] <= (s['end'] or time.time())])
            row = {'id': self._sid(s['start']), 'user_id': self.uid, 'class_label': s['class'], 'assignment_label': s.get('assignment') or None,
                   'started_at': iso(s['start']), 'ended_at': iso(s['end']) if s['end'] else None, 'seconds': int(s.get('seconds', 0)),
                   'clean': tl['clean'], 'flagged': tl['flagged'], 'overridden': tl['overridden'], 'updated_at': iso(time.time())}
            sig = json.dumps({k: v for k, v in row.items() if k != 'updated_at'}, sort_keys=True)
            if self._sent_sessions.get(row['id']) != sig:
                rows.append(row); self._sent_sessions[row['id']] = sig
        if rows:
            try:
                self._rest('POST', 'sessions?on_conflict=id', rows, prefer='resolution=merge-duplicates,return=minimal')
            except CloudError:
                for r in rows:
                    self._sent_sessions.pop(r['id'], None)
                raise
        # 3) per-day counts (streaks and Insights on a partner's profile)
        per = {}
        for s in sessions:
            d = datetime.fromtimestamp(s['start']).date().isoformat()
            x = per.setdefault(d, {'seconds': 0, 'sessions': 0, 'clean': 0, 'flagged': 0, 'overridden': 0})
            x['seconds'] += int(s.get('seconds', 0)); x['sessions'] += 1
        by_day = {}
        for m in bridge.dedupe(msgs):
            by_day.setdefault(datetime.fromtimestamp(m['t']).date().isoformat(), []).append(m)
        for d, ms in by_day.items():
            tl = bridge.tally(ms)
            x = per.setdefault(d, {'seconds': 0, 'sessions': 0, 'clean': 0, 'flagged': 0, 'overridden': 0})
            x.update(clean=tl['clean'], flagged=tl['flagged'], overridden=tl['overridden'])
        recent = sorted(per)[-120:]
        daily = [{'user_id': self.uid, 'day': d, 'checked': per[d]['clean'] + per[d]['flagged'] + per[d]['overridden'], **per[d]} for d in recent]
        sig = json.dumps(daily, sort_keys=True)
        if daily and sig != self._sent_sessions.get('__daily__'):
            self._rest('POST', 'daily?on_conflict=user_id,day', daily, prefer='resolution=merge-duplicates,return=minimal')
            self._sent_sessions['__daily__'] = sig

    def _notify_new_overrides(self):
        """A quiet macOS notification when someone you watch overrides a warning."""
        try:
            import watcher
            ov = self.overview()
        except CloudError:
            return
        last = self.c.get('last_notified_t', time.time())
        fresh = [e for e in ov['feed'] if from_iso(e['at']) > last]
        if fresh:
            self.c['last_notified_t'] = max(from_iso(e['at']) for e in fresh)
            self._save()
            who = (fresh[0].get('who') or {}).get('display_name') or 'A friend'
            watcher.notify('HonestHands', f'{who} sent a prompt despite a warning' + (f' (+{len(fresh) - 1} more)' if len(fresh) > 1 else ''))
