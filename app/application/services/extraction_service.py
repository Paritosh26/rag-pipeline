from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz


class ExtractionService:
    """Extract text and lightweight metadata from source documents.

    Parsing, cleaning, and metadata extraction are all facets of turning a raw
    file into ingestible content, so they live together as one capability.
    """

    _TITLE_PATTERN = re.compile(r'title:\s*(.+?)(?:\n|\.)', re.IGNORECASE)
    _AUTHOR_PATTERN = re.compile(r'authors?:\s*(.+?)(?:\n|\.)', re.IGNORECASE)
    _KEYWORD_PATTERN = re.compile(r'keywords?:\s*(.+?)(?:\n|\.)', re.IGNORECASE)
    _YEAR_PATTERN = re.compile(r'\b((?:19|20)\d{2})\b')
    _MEDLINE_FIELD = re.compile(r'^([A-Z]{2,4})\s*-\s?(.*)$')

    def __init__(self, supported_extensions: tuple[str, ...] = ('.pdf', '.txt')) -> None:
        self.supported_extensions = supported_extensions

    def extract_text_from_path(self, path: str | Path) -> str:
        """Extract raw text from a supported file and return cleaned text."""
        file_path = Path(path)
        if file_path.suffix.lower() == '.pdf':
            raw_text = self._read_pdf(file_path)
        elif file_path.suffix.lower() == '.txt':
            raw_text = file_path.read_text(encoding='utf-8')
        else:
            raise ValueError(f'Unsupported file type: {file_path.suffix}')
        if raw_text.lstrip().startswith('PMID-'):
            raw_text = self._medline_content(raw_text)
        return self.clean_text(raw_text)

    def _medline_content(self, text: str) -> str:
        """Reduce a raw MEDLINE/PubMed record to its title and abstract.

        MEDLINE records are mostly bibliographic bookkeeping (PMID, ISSN,
        volume/issue, dates, ...) with the actual clinical content in just the
        TI and AB fields. Chunking the whole record made the first chunk of
        every article pure header noise that ranked in top-k retrieval ahead
        of real content for many queries, occasionally causing the answer
        step to wrongly claim "no information" when it existed in a
        lower-ranked chunk. Keeping only TI/AB fixes that at the source.
        """
        fields: dict[str, list[str]] = {}
        current_tag: str | None = None
        for line in text.splitlines():
            match = None if line.startswith(' ') else self._MEDLINE_FIELD.match(line)
            if match:
                current_tag = match.group(1)
                fields.setdefault(current_tag, []).append(match.group(2))
            elif current_tag and line.startswith(' '):
                fields[current_tag][-1] += ' ' + line.strip()

        title = ' '.join(fields.get('TI', []))
        abstract = ' '.join(fields.get('AB', []))
        content = f'{title}\n\n{abstract}'.strip()
        return content or text

    def clean_text(self, text: str) -> str:
        """Normalize whitespace, remove control characters, and collapse repeated spaces."""
        if not text:
            return ''

        cleaned = text.replace('\x00', ' ')
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def extract_metadata(self, path: str | Path, text: str | None = None) -> dict[str, Any]:
        """Extract lightweight metadata (title, authors, keywords, year) from document text."""
        file_path = Path(path)
        content = text if text is not None else file_path.read_text(encoding='utf-8', errors='ignore')
        return {
            'title': self._find_first_match(self._TITLE_PATTERN, content),
            'authors': self._split_list(self._AUTHOR_PATTERN, content),
            'keywords': self._split_list(self._KEYWORD_PATTERN, content),
            'publication_year': self._extract_year(content),
            'source_file': str(file_path),
        }

    def _read_pdf(self, file_path: Path) -> str:
        document = fitz.open(file_path)
        try:
            return '\n'.join(page.get_text() for page in document)
        finally:
            document.close()

    def _find_first_match(self, pattern: re.Pattern[str], text: str) -> str | None:
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    def _split_list(self, pattern: re.Pattern[str], text: str) -> list[str]:
        match = pattern.search(text)
        if not match:
            return []
        return [item.strip() for item in match.group(1).split(',') if item.strip()]

    def _extract_year(self, text: str) -> int | None:
        matches = self._YEAR_PATTERN.findall(text)
        return int(matches[-1]) if matches else None
