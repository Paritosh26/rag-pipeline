from pathlib import Path

from app.application.services.extraction_service import ExtractionService


def test_clean_text_removes_noise_and_normalizes_whitespace() -> None:
    service = ExtractionService()
    raw_text = "\n\tThis   is\n\n a   sample" + chr(0) + " text.\n\n"

    cleaned = service.clean_text(raw_text)

    assert cleaned == "This is a sample text."


def test_extract_text_from_document_path_uses_cleaned_content(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("\n\tAlpha   Beta\n\n", encoding="utf-8")

    service = ExtractionService()
    cleaned = service.extract_text_from_path(file_path)

    assert cleaned == "Alpha Beta"


def test_extract_text_strips_medline_header_and_keeps_title_and_abstract(tmp_path: Path) -> None:
    file_path = tmp_path / 'pubmed-99999999.txt'
    file_path.write_text(
        'PMID- 99999999\n'
        'OWN - NLM\n'
        'STAT- MEDLINE\n'
        'IS  - 1533-4406 (Electronic)\n'
        'VI  - 376\n'
        'DP  - 2017 Apr 20\n'
        'TI  - Sickle Cell Disease.\n'
        'PG  - 1561-1573\n'
        'AB  - CLINICAL CHARACTERISTICS: Sickle cell disease is characterized by\n'
        '      vaso-occlusive events and chronic hemolytic anemia. DIAGNOSIS/TESTING:\n'
        '      established by hemoglobin assay or molecular genetic testing.\n'
        'FAU - Rees, David C\n',
        encoding='utf-8',
    )

    service = ExtractionService()
    content = service.extract_text_from_path(file_path)

    assert 'PMID' not in content
    assert 'OWN' not in content
    assert 'Sickle Cell Disease' in content
    assert 'DIAGNOSIS/TESTING' in content
    assert 'molecular genetic testing' in content


def test_extract_text_leaves_non_medline_content_untouched(tmp_path: Path) -> None:
    file_path = tmp_path / 'notes.txt'
    file_path.write_text('Plain notes about a disease, not a MEDLINE record.', encoding='utf-8')

    service = ExtractionService()
    content = service.extract_text_from_path(file_path)

    assert content == 'Plain notes about a disease, not a MEDLINE record.'


def test_extract_metadata_extracts_title_and_keywords(tmp_path: Path) -> None:
    file_path = tmp_path / 'paper.txt'
    file_path.write_text('Title: Cancer Biomarkers in 2024. Authors: Jane Doe, John Smith. Keywords: oncology, biomarkers.', encoding='utf-8')

    service = ExtractionService()
    metadata = service.extract_metadata(file_path)

    assert metadata['title'] == 'Cancer Biomarkers in 2024'
    assert metadata['authors'] == ['Jane Doe', 'John Smith']
    assert metadata['keywords'] == ['oncology', 'biomarkers']
    assert metadata['publication_year'] == 2024
