"""Rule-based dictation cleanup + guard. No language model, so speech can never be treated as a prompt.

rule_clean(raw)  -> cleaned text (instant)
guard(raw, model_out, fallback) -> model_out only if it is plainly the same words as raw, else fallback
"""
import re

_FILLER = re.compile(
    r"(?<![\w'-])(?:um+|uh+|uhm+|er+m?|ah+|hmm+|you know|i mean|sort of|kind of like|like,)(?![\w'-])[,]?\s*",
    re.I)
# "like" as a filler only when set off by commas: ", like," -> handled by the "like," token above.
_SPOKEN_PUNCT = [
    (r"\s*\bquestion mark\b", "?"), (r"\s*\bexclamation (?:mark|point)\b", "!"),
    (r"\s*\bfull stop\b|\s*\bperiod\b(?=\s|$)", "."), (r"\s*\bcomma\b(?=\s|$)", ","),
    (r"\s*\bcolon\b(?=\s|$)", ":"), (r"\s*\bsemicolon\b", ";"),
    (r"\bnew paragraph\b\s*", "\n\n"), (r"\bnew line\b\s*", "\n"),
    (r"\bopen quote\b\s*", '"'), (r"\s*\bclose quote\b", '"'),
]
_DAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_MONTHS = r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
_NUM = r"(?:\d+(?::\d\d)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_CORR = r"(?:no,? wait|wait,? no|no no|I mean|sorry|actually no|scratch that)"


def _self_correct(t: str) -> str:
    for cls in (_DAYS, _MONTHS, _NUM):
        t = re.sub(rf"\b{cls}\b\s*,?\s*{_CORR}\s*,?\s*(?=\b{cls}\b)", "", t, flags=re.I)
    return t


def rule_clean(raw: str) -> str:
    t = " " + raw.strip() + " "
    t = _self_correct(t)
    t = _FILLER.sub(" ", t)
    for pat, rep in _SPOKEN_PUNCT:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\s+([,.;:?!])", r"\1", t)
    t = re.sub(r"([,.;:?!])\1+", r"\1", t)
    t = re.sub(r"([?!])\.", r"\1", t)
    t = re.sub(r"([?!])[,.;]", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    t = re.sub(r"^[,;\s]+", "", t)
    if not re.search(r"\w", t):
        return raw.strip()
    t = re.sub(r"\bi\b(?=[ ',.?!]|$)", "I", t)
    # capitalize sentence starts
    t = re.sub(r"(^|[.?!]\s+|\n)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    if t and t[-1] not in ".?!\"":
        t += "."
    return t


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def guard(raw: str, out: str, fallback: str) -> str:
    """Accept a model rewrite only if it only rearranges/removes the speaker's own words."""
    rw, ow = _words(raw), _words(out)
    if not ow or not rw:
        return fallback
    if not 0.6 * len(rw) <= len(ow) <= 1.1 * len(rw):
        return fallback
    pool = {}
    for w in rw:
        pool[w] = pool.get(w, 0) + 1
    novel = 0
    for w in ow:
        if pool.get(w, 0) > 0:
            pool[w] -= 1
        else:
            novel += 1
    return out if novel <= max(1, int(0.08 * len(ow))) else fallback
