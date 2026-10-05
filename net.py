"""One TLS setting for every HTTPS call (model download, Supabase).

The packaged app has no certificate list of its own, so Python's default fails with CERTIFICATE_VERIFY_FAILED on a Mac
that never ran the "Install Certificates" step. Use certifi if present, else the Mac's own bundle."""
import os
import ssl

_ctx = None


def context():
    global _ctx
    if _ctx is None:
        cafile = None
        try:
            import certifi
            cafile = certifi.where()
        except Exception:
            pass
        if not cafile or not os.path.exists(cafile):
            cafile = '/etc/ssl/cert.pem' if os.path.exists('/etc/ssl/cert.pem') else None
        _ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    return _ctx
