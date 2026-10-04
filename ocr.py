"""Reads the text in a picture, entirely on this Mac, using Apple's built-in Vision framework.
Nothing is uploaded and no model is downloaded. Returns '' if the picture has no readable text (a photo, a diagram,
handwriting Vision can't make out)."""
import base64
import re


def _bytes(data):
    """Accepts raw bytes or a data: URL (what the browser extension sends)."""
    if isinstance(data, str):
        data = data.split(',', 1)[1] if data.startswith('data:') else data
        return base64.b64decode(data)
    return bytes(data)


def read_text(image, max_chars=6000):
    try:
        import Vision
        from Foundation import NSData
        raw = _bytes(image)
        ns = NSData.dataWithBytes_length_(raw, len(raw))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(ns, {})
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(True)
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            return ''
        lines = []
        for obs in (req.results() or []):
            cands = obs.topCandidates_(1)
            if cands and cands[0].confidence() >= 0.3:
                lines.append(str(cands[0].string()))
        return re.sub(r'[ \t]+', ' ', '\n'.join(lines)).strip()[:max_chars]
    except Exception as e:
        print('[ocr] could not read the picture:', e, flush=True)
        return ''
