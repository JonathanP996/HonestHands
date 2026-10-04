"""The AI that does the guarding. Three choices:
  builtin  - runs a small model INSIDE this app with llama-cpp-python (default)
  ollama   - uses Ollama if you already have it
  keywords - no AI, keyword rules only

The built-in model runs in-process (no separate program is launched), which keeps
one app = one process and avoids any relaunch loops.
"""
import importlib.util
import json
import threading
import urllib.request

from store import APP_DIR

MODEL_DIR = APP_DIR / 'models'
OLLAMA = 'http://127.0.0.1:11434'
UA = {'User-Agent': 'HonestHands/1.0'}

MODELS = {
    'small': {
        'label': 'Small: fastest, about 2 GB download, fine on 8 GB Macs',
        'file': 'qwen2.5-3b-instruct-q4_k_m.gguf',
        'url': 'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf',
    },
    'large': {
        'label': 'Larger: more accurate, about 4.7 GB download, needs 16 GB of memory',
        'file': 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
        'url': 'https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
    },
}


def http_json(url, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=dict(UA, **{'Content-Type': 'application/json'}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find('{'), text.rfind('}')
    if s != -1 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            pass
    raise ValueError('the model did not return valid JSON')


def llama_available():
    return importlib.util.find_spec('llama_cpp') is not None


class Engine:
    def __init__(self, store):
        self.store = store
        self.llama = None          # the loaded in-process model (builtin)
        self.state = 'idle'        # idle | needs_setup | downloading | starting | ready | off | error
        self.message = ''
        self.progress = None
        self._busy = False
        self._call_lock = threading.Lock()
        self._gen = 0              # bumped on each (re)start so stale threads bail out
        self._dl_bg = False
        self.override = None       # a different, already-installed model used until the chosen one is downloaded

    @property
    def cfg(self):
        return self.store.data['engine']

    def model(self):
        return MODELS.get(self.override or self.cfg.get('model'), MODELS['small'])

    def model_path(self):
        return MODEL_DIR / self.model()['file']

    def installed(self):
        if self.cfg['backend'] == 'ollama':
            return True
        return llama_available() and self.model_path().exists()

    def ready(self):
        b = self.cfg['backend']
        if b == 'keywords':
            return False
        if b == 'ollama':
            return self.state == 'ready'
        return self.state == 'ready' and self.llama is not None

    def status(self):
        return {
            'backend': self.cfg['backend'], 'model': self.cfg.get('model', 'small'),
            'ollama_model': self.cfg.get('ollama_model', 'qwen2.5:3b'),
            'models': {k: v['label'] for k, v in MODELS.items()},
            'installed': self.installed(), 'state': self.state, 'message': self.message,
            'progress': self.progress, 'ready': self.ready(), 'busy': self._busy,
            'has_runtime': llama_available(),
        }

    def _set(self, state, message=''):
        self.state, self.message = state, message

    # ---------- start / stop ----------
    def autostart(self):
        b = self.cfg['backend']
        # If the chosen model isn't downloaded but another one is, use it now rather than
        # silently falling back to keyword-only checking. Choosing a model in Settings downloads it.
        self.override = None
        if b == 'builtin' and llama_available() and not (MODEL_DIR / self.model()['file']).exists():
            for key, m in MODELS.items():
                if (MODEL_DIR / m['file']).exists():
                    self.override = key
                    break
            if self.override:
                threading.Thread(target=self._finish_chosen_download, daemon=True).start()
        if b == 'keywords':
            self._set('off', 'Using keyword rules only.')
        elif b == 'builtin' and not self.installed():
            if not llama_available():
                self._set('needs_setup', 'The built-in AI runtime isn\'t available in this copy. Use Ollama, or keyword rules.')
            else:
                self._set('needs_setup', 'The AI guard needs a one-time model download. Set it up in Settings.')
        else:
            self.start()

    def start(self):
        if self._busy:
            return
        self._gen += 1
        gen = self._gen
        threading.Thread(target=self._start, args=(gen,), daemon=True).start()

    def _start(self, gen):
        self._busy = True
        try:
            self.stop_server()
            b = self.cfg['backend']
            if b == 'keywords':
                self._set('off', 'Using keyword rules only.')
            elif b == 'ollama':
                self._start_ollama(gen)
            else:
                self._start_builtin(gen)
        except Exception as e:
            if gen == self._gen:
                self._set('error', str(e))
        finally:
            self._busy = False
            self.progress = None

    def stop_server(self):
        self.llama = None  # free the model; nothing else to stop (no subprocess)

    def _start_builtin(self, gen):
        if not llama_available():
            raise RuntimeError('The built-in AI runtime isn\'t installed. Use Ollama, or keyword rules, '
                               'or rebuild the app so it bundles the engine.')
        if not self.model_path().exists():
            self._download_model(gen)
        if gen != self._gen:
            return
        self._set('starting', 'Loading the AI guard…')
        from llama_cpp import Llama
        llama = Llama(
            model_path=str(self.model_path()),
            n_ctx=8192,
            n_gpu_layers=-1,   # offload everything to the Mac's GPU (Metal)
            verbose=False,
        )
        if gen != self._gen:
            return
        self.llama = llama
        self._set('ready', 'AI guard is ready.')

    def _download(self, url, dest, label, gen):
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + '.part')
        have = part.stat().st_size if part.exists() else 0     # resume an interrupted download
        req = urllib.request.Request(url, headers=dict(UA, **({'Range': f'bytes={have}-'} if have else {})))
        with urllib.request.urlopen(req, timeout=60) as r:
            resumed = have > 0 and getattr(r, 'status', 200) == 206
            f = open(part, 'ab' if resumed else 'wb')
            total = int(r.headers.get('Content-Length') or 0) + (have if resumed else 0)
            done = have if resumed else 0
            while True:
                if gen is not None and gen != self._gen:
                    f.close(); return
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                self.progress = {'label': label, 'done': done, 'total': total}
            f.close()
        part.replace(dest)

    def _finish_chosen_download(self):
        """Keeps downloading the model chosen in Settings (resuming a partial file) while the
        installed one does the guarding, then switches over when it's complete."""
        chosen = MODELS.get(self.cfg.get('model'))
        if not chosen or self._dl_bg:
            return
        self._dl_bg = True
        try:
            self._download(chosen['url'], MODEL_DIR / chosen['file'], 'AI model', None)
            if (MODEL_DIR / chosen['file']).exists():
                self.override = None
                self.start()          # reload with the model you chose
        except Exception as ex:
            print('background model download stopped:', ex)
        finally:
            self._dl_bg = False
            self.progress = None

    def _download_model(self, gen):
        self._set('downloading', 'Downloading the AI model (one time).')
        self._download(self.model()['url'], self.model_path(), 'AI model', gen)

    def _start_ollama(self, gen):
        self._set('starting', 'Connecting to Ollama…')
        try:
            tags = http_json(f'{OLLAMA}/api/tags', timeout=3)
        except Exception:
            raise RuntimeError('Ollama isn\'t running. Open the Ollama app, then click Apply again.')
        name = self.cfg.get('ollama_model') or 'qwen2.5:3b'
        have = {m.get('name') for m in tags.get('models', [])}
        if name not in have and f'{name}:latest' not in have:
            self._set('downloading', f'Ollama is downloading {name}…')
            req = urllib.request.Request(f'{OLLAMA}/api/pull', data=json.dumps({'model': name, 'stream': True}).encode(),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=3600) as r:
                for line in r:
                    if gen != self._gen:
                        return
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    if msg.get('error'):
                        raise RuntimeError(f'Ollama: {msg["error"]}')
                    if msg.get('total'):
                        self.progress = {'label': name, 'done': msg.get('completed', 0), 'total': msg['total']}
        self.chat_json('Reply with the JSON {"ok": true}.', 'ping', timeout=180, max_tokens=10)
        self._set('ready', f'AI guard is ready (Ollama, {name}).')

    # ---------- asking the model ----------
    def chat_raw(self, system, user, timeout=20, max_tokens=200):
        """Returns the model's raw text. Gives up (rather than queueing forever) if another call hogs the model."""
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        if not self._call_lock.acquire(timeout=max(1, timeout)):
            raise TimeoutError('the AI guard was busy')
        try:
            if self.cfg['backend'] == 'ollama':
                r = http_json(f'{OLLAMA}/api/chat', {
                    'model': self.cfg.get('ollama_model') or 'qwen2.5:3b', 'messages': msgs, 'stream': False,
                    'format': 'json', 'keep_alive': '60m',
                    'options': {'temperature': 0, 'num_predict': max_tokens, 'num_ctx': 8192},
                }, timeout=timeout)
                return r['message']['content']
            if self.llama is None:
                raise RuntimeError('the AI guard is not loaded')
            out = self.llama.create_chat_completion(messages=msgs, temperature=0, max_tokens=max_tokens)  # no JSON grammar: it can abort llama.cpp
            return out['choices'][0]['message']['content']
        finally:
            self._call_lock.release()

    def chat_json(self, system, user, timeout=20, max_tokens=200):
        return parse_json(self.chat_raw(system, user, timeout, max_tokens))
