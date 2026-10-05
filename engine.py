"""The AI that does the guarding: one small model that runs privately on this Mac.

It runs INSIDE this app with llama-cpp-python (no separate program, nothing uploaded). There is a single model on
purpose: fewer choices, nothing to misconfigure. If it isn't ready yet, the guard falls back to keyword rules for a moment.
"""
import importlib.util
import json
import threading
import urllib.request

from store import APP_DIR

AI_NAME = 'Handrail'          # what the built-in AI is called in the app
MODEL_DIR = APP_DIR / 'models'
UA = {'User-Agent': 'HonestHands/1.0'}

MODELS = {
    'small': {
        'label': f'{AI_NAME}: private, runs on this Mac, about 2 GB',
        'file': 'qwen2.5-3b-instruct-q4_k_m.gguf',
        'url': 'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf',
        'size': 2104932768,   # exact bytes: a file of any other size is incomplete or corrupt and gets downloaded again
    },
}


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
        self.llama = None          # the loaded in-process model
        self.state = 'idle'        # idle | needs_setup | downloading | starting | ready | error
        self.message = ''
        self.progress = None
        self._busy = False
        self._call_lock = threading.Lock()
        self._gen = 0              # bumped on each (re)start so stale threads bail out

    @property
    def cfg(self):
        return self.store.data['engine']

    def model(self):
        return MODELS['small']

    def model_path(self):
        return MODEL_DIR / self.model()['file']

    def installed(self):
        p = self.model_path()
        return llama_available() and p.exists() and p.stat().st_size == self.model()['size']

    def ready(self):
        return self.state == 'ready' and self.llama is not None

    def status(self):
        m = self.model()
        return {
            'name': AI_NAME, 'label': m['label'], 'size_gb': round(m['size'] / 1e9, 1),
            'installed': self.installed(), 'state': self.state, 'message': self.message,
            'progress': self.progress, 'ready': self.ready(), 'busy': self._busy,
            'has_runtime': llama_available(),
        }

    def _set(self, state, message=''):
        self.state, self.message = state, message

    # ---------- start / stop ----------
    def autostart(self):
        if not llama_available():
            self._set('needs_setup', f'{AI_NAME} can\'t run in this copy of the app (its engine is missing).')
        elif not self.installed():
            self._set('needs_setup', f'{AI_NAME} needs a one-time {self.status()["size_gb"]} GB download.')
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
            raise RuntimeError(f'{AI_NAME}\'s engine isn\'t installed. Rebuild the app so it bundles the engine.')
        if not self.installed():
            p = self.model_path()
            if p.exists() and p.stat().st_size > self.model()['size']:
                p.unlink()             # bigger than it should be: corrupt, start clean
            self._download_model(gen)
        if gen != self._gen:
            return
        self._set('starting', f'Loading {AI_NAME}…')
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
        self._set('ready', f'{AI_NAME} is ready.')

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
        if part.stat().st_size != self.model()['size']:
            part.unlink(missing_ok=True)                        # incomplete or corrupt: never keep it
            raise RuntimeError('The download didn\'t finish cleanly. Check your connection and try again.')
        part.replace(dest)

    def _download_model(self, gen):
        self._set('downloading', f'Downloading {AI_NAME} (one time).')
        self._download(self.model()['url'], self.model_path(), AI_NAME, gen)

    # ---------- asking it questions ----------
    def chat_raw(self, system, user, timeout=20, max_tokens=200):
        """Returns the model's raw text. Gives up (rather than queueing forever) if another call hogs the model."""
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        if not self._call_lock.acquire(timeout=max(1, timeout)):
            raise TimeoutError('the AI guard was busy')
        try:
            if self.llama is None:
                raise RuntimeError('the AI guard is not loaded')
            out = self.llama.create_chat_completion(messages=msgs, temperature=0, max_tokens=max_tokens)  # no JSON grammar: it can abort llama.cpp
            return out['choices'][0]['message']['content']
        finally:
            self._call_lock.release()

    def chat_json(self, system, user, timeout=20, max_tokens=200):
        return parse_json(self.chat_raw(system, user, timeout, max_tokens))
