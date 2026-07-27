from __future__ import annotations

import re
from pathlib import Path

from Bio import Entrez

_PMID_LINE = re.compile(r'^PMID-\s*(\d+)', re.MULTILINE)


class EntrezPubMedFetcher:
    """Fetch MEDLINE-format PubMed records via NCBI E-utilities and write them
    as raw ingestion files.

    Output is written in the same format and location convention as manually
    placed files (`data/raw/<collection>/pubmed-<pmid>.txt`), so the existing
    checksum-gated `/ingest-pipeline` flow works on it unchanged. This is a
    manually-triggered fetch, not scheduled -- there is no automation wiring it
    up to run on its own.
    """

    def __init__(self, email: str, api_key: str | None = None, raw_data_root: str | Path = 'data/raw') -> None:
        self.email = email
        self.api_key = api_key
        self.raw_data_root = Path(raw_data_root)

    def fetch_and_save(self, query: str, collection: str, max_results: int = 20) -> list[Path]:
        Entrez.email = self.email
        if self.api_key:
            Entrez.api_key = self.api_key

        with Entrez.esearch(db='pubmed', term=query, retmax=max_results) as handle:
            search_result = Entrez.read(handle)
        pmids = list(search_result.get('IdList', []))
        if not pmids:
            return []

        with Entrez.efetch(db='pubmed', id=','.join(pmids), rettype='medline', retmode='text') as handle:
            raw_text = handle.read()

        collection_dir = self.raw_data_root / collection
        collection_dir.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for record_text in self._split_records(raw_text):
            match = _PMID_LINE.search(record_text)
            if not match:
                continue
            file_path = collection_dir / f'pubmed-{match.group(1)}.txt'
            file_path.write_text(record_text, encoding='utf-8')
            written.append(file_path)
        return written

    def _split_records(self, raw_text: str) -> list[str]:
        blocks: list[str] = []
        current: list[str] = []
        for line in raw_text.splitlines(keepends=True):
            if line.startswith('PMID-') and current:
                blocks.append(''.join(current))
                current = []
            current.append(line)
        if current:
            blocks.append(''.join(current))
        return blocks
