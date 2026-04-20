#!/usr/bin/env python3
"""
Shared citation / bibkey helpers for both build_slr_manuscript.py (LaTeX)
and build_q1_report.py (docx).

Why a module: the LaTeX builder wants \cite{bibkey} output, the docx builder
wants "Surname et al. (Year)" prose with a numbered reference list. Both
consume the same per-paper metadata and both resolve REC-xxx dedup_ids to a
normalised, ASCII-safe author-year reference.
"""
import re
import unicodedata

# ── Unicode → ASCII ────────────────────────────────────────────────────────

# Manual transliteration for letters that don't decompose via NFKD
_NON_DECOMPOSABLE = str.maketrans({
    "ı": "i", "İ": "I", "ł": "l", "Ł": "L",
    "ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae",
    "œ": "oe", "Œ": "Oe", "ß": "ss",
    "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D",
})


def to_ascii(s):
    """Best-effort ASCII transliteration (Uyanık → Uyanik, Hernández → Hernandez)."""
    if not s:
        return ""
    s = s.translate(_NON_DECOMPOSABLE)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


# ── Surname / bibkey ──────────────────────────────────────────────────────

def surname_from_authors(authors_str):
    """Return best-guess first-author surname from a raw author list.

    Input convention: "FirstMiddle LastName, FirstName LastName, ..."
    Strategy: take the first author (before the first comma), then take the
    last whitespace token that is not a single initial. Handles common
    suffixes like Jr. / III.
    """
    if not authors_str:
        return "Anon"
    first = authors_str.split(",")[0].strip()
    if not first:
        return "Anon"
    first = to_ascii(first)
    tokens = first.split()
    while tokens and tokens[-1].lower().rstrip(".") in ("jr", "sr", "ii", "iii", "iv"):
        tokens.pop()
    for tok in reversed(tokens):
        plain = re.sub(r"[^A-Za-z]", "", tok)
        if len(plain) >= 2:
            return plain
    return tokens[-1] if tokens else "Anon"


def bibkey(r, used):
    """Generate a stable BibTeX key from first author's surname + year."""
    authors = r.get("authors", "") or ""
    first_author = authors.split(",")[0].strip()
    first_author_ascii = to_ascii(first_author)
    tokens = [t for t in first_author_ascii.split() if t and t.rstrip(".") != ""]
    surname = ""
    for tok in reversed(tokens):
        plain = re.sub(r"[^A-Za-z]", "", tok)
        if len(plain) >= 2:
            surname = plain
            break
    if not surname and tokens:
        surname = re.sub(r"[^A-Za-z]", "", tokens[-1])
    fa = surname.lower() or "anon"
    yr = re.sub(r"[^0-9]", "", str(r.get("year", "") or "na"))[:4] or "nd"
    base = f"{fa}{yr}"
    key = base; i = 1
    while key in used:
        key = f"{base}{chr(96+i)}"
        i += 1
    used.add(key)
    return key


def latex_escape(s):
    if s is None:
        return ""
    s = str(s)
    reps = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}", "<": r"\textless{}", ">": r"\textgreater{}"}
    for k, v in reps.items():
        s = s.replace(k, v)
    return s


# ── Narrative REC-xxx rewriters ───────────────────────────────────────────

def _drop_cited_trailer(text):
    """Strip trailing 'Cited: REC-...' line(s) from a narrative."""
    return re.sub(r"\n\s*Cited:.*$", "", text, flags=re.DOTALL).strip()


def rewrite_narrative_latex(text, key_map, corpus_by_id):
    """Convert REC-xxx references → \\cite{bibkey} LaTeX form.

    - First mention gets "Surname et al.~\\cite{bibkey}"
    - Subsequent plain mentions get "\\cite{bibkey}"
    - Parenthesised `(REC-xxx)` becomes `~\\cite{bibkey}` (author already precedes it)
    - Runs of comma-separated RECs collapse to a single \\cite{a,b,c}
    """
    text = _drop_cited_trailer(text)

    def merge_run(match):
        ids = re.findall(r"REC-\d+", match.group(0))
        keys = [key_map.get(i) for i in ids]
        keys = [k for k in keys if k]
        if not keys:
            return match.group(0)
        return "\\cite{" + ",".join(keys) + "}"

    text = re.sub(
        r"REC-\d+(?:\s*[,;]?\s*(?:and\s+)?REC-\d+){1,}",
        merge_run, text)

    def paren_single(match):
        rid = match.group(1)
        key = key_map.get(rid)
        return f"~\\cite{{{key}}}" if key else match.group(0)

    text = re.sub(r"\s*\((REC-\d+)\)", paren_single, text)

    seen = set()

    def replace_single(match):
        rid = match.group(0)
        key = key_map.get(rid)
        if not key:
            return rid
        paper = corpus_by_id.get(rid, {})
        if rid in seen:
            return f"\\cite{{{key}}}"
        seen.add(rid)
        surname = latex_escape(surname_from_authors(paper.get("authors", "")))
        return f"{surname} et al.~\\cite{{{key}}}"

    return re.sub(r"REC-\d+", replace_single, text)


CITE_SENTINEL = "\uE000CITE:{n}\uE000"  # Private-use Unicode — never appears in real text
CITE_SENTINEL_RE = re.compile(r"\uE000CITE:(\d+)\uE000")


def rewrite_narrative_docx(text, corpus_by_id):
    """Convert REC-xxx references → 'Surname et al. (Year) <sentinel>' plain text
    suitable for a .docx deliverable. Returns (rewritten_text, ordered_keys).

    Sentinels `\\uE000CITE:N\\uE000` carry the local reference number; the
    caller is expected to finalise them to `[N']` where N' is a document-wide
    renumbered index (the sentinel avoids clashing with literal `[N]` quoted
    from the papers themselves).
    """
    text = _drop_cited_trailer(text)

    order = []  # first-mention order; each REC appears at most once

    def register(rid):
        if rid not in order:
            order.append(rid)
        return order.index(rid) + 1

    def merge_run(match):
        ids = re.findall(r"REC-\d+", match.group(0))
        nums = []
        for rid in ids:
            if rid in corpus_by_id:
                nums.append(register(rid))
        if not nums:
            return match.group(0)
        return "[" + ", ".join(CITE_SENTINEL.format(n=n) for n in nums) + "]"

    text = re.sub(
        r"REC-\d+(?:\s*[,;]?\s*(?:and\s+)?REC-\d+){1,}",
        merge_run, text)

    def paren_single(match):
        rid = match.group(1)
        if rid not in corpus_by_id:
            return match.group(0)
        n = register(rid)
        return f" [{CITE_SENTINEL.format(n=n)}]"

    text = re.sub(r"\s*\((REC-\d+)\)", paren_single, text)

    seen = set()

    def replace_single(match):
        rid = match.group(0)
        paper = corpus_by_id.get(rid)
        if not paper:
            return rid
        n = register(rid)
        if rid in seen:
            return f"[{CITE_SENTINEL.format(n=n)}]"
        seen.add(rid)
        surname = surname_from_authors(paper.get("authors", ""))
        year = re.sub(r"[^0-9]", "", str(paper.get("year", "") or ""))[:4] or "n.d."
        return f"{surname} et al. ({year}) [{CITE_SENTINEL.format(n=n)}]"

    text = re.sub(r"REC-\d+", replace_single, text)
    return text, order


def build_references_list(ordered_ids, corpus_by_id):
    """Build an ordered list of (n, formatted_reference_string) tuples for a
    docx numbered reference list."""
    out = []
    for i, rid in enumerate(ordered_ids, 1):
        p = corpus_by_id.get(rid, {})
        authors = p.get("authors", "") or "Anonymous"
        year = p.get("year", "") or "n.d."
        title = p.get("title", "") or ""
        venue = p.get("venue", "") or ""
        doi = p.get("doi", "") or ""
        ref = f"[{i}] {authors} ({year}). {title}"
        if venue:
            ref += f". {venue}"
        if doi:
            ref += f". DOI: {doi}"
        out.append((i, ref))
    return out
