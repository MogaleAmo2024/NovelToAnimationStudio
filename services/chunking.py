import re

CHAPTER_PATTERNS = [
    re.compile(r"^\s*chapter\s+[ivxlcdm\d]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*part\s+[ivxlcdm\d]+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*第\s*\d+\s*章", re.MULTILINE),  # Chinese
]

MAX_CHUNK_CHARS = 6000
MIN_CHUNK_CHARS = 2000


def _split_by_chapters(text: str) -> list[str]:
    """Split text at chapter/part markers if any exist."""
    indices = []
    for pat in CHAPTER_PATTERNS:
        indices.extend(m.start() for m in pat.finditer(text))
    indices = sorted(set(indices))
    if len(indices) < 3:
        return [text]
    if indices[0] > 0:
        indices = [0] + indices
    return [text[i:j] for i, j in zip(indices, indices[1:] + [len(text)])]


def _split_by_paragraphs(text: str, max_chars: int) -> list[str]:
    """Greedy pack paragraphs into chunks under max_chars."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf, size = [], [], 0
    for p in paras:
        if size + len(p) + 2 > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf, size = [p], len(p)
        else:
            buf.append(p)
            size += len(p) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def split_text(text: str) -> list[str]:
    """
    1. If chapters exist and each is a sensible size, use them.
    2. Otherwise, pack paragraphs into ~6k char chunks.
    3. Any chunk over MAX_CHUNK_CHARS gets further split by paragraphs.
    """
    text = text.strip()
    if not text:
        return []

    chapter_chunks = _split_by_chapters(text)
    if len(chapter_chunks) > 1:
        # merge tiny chapters, split huge ones
        normalized = []
        buf = ""
        for c in chapter_chunks:
            if len(c) > MAX_CHUNK_CHARS:
                if buf:
                    normalized.append(buf)
                    buf = ""
                normalized.extend(_split_by_paragraphs(c, MAX_CHUNK_CHARS))
            elif len(buf) + len(c) < MIN_CHUNK_CHARS:
                buf += "\n\n" + c
            else:
                if buf:
                    normalized.append(buf)
                buf = c
        if buf:
            normalized.append(buf)
        return [c for c in normalized if c.strip()]

    # no chapter structure — pack paragraphs
    chunks = _split_by_paragraphs(text, MAX_CHUNK_CHARS)
    return [c for c in chunks if c.strip()]