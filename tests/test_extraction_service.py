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


def test_extract_metadata_parses_medline_title_authors_keywords_year(tmp_path: Path) -> None:
    file_path = tmp_path / 'pubmed-11111111.txt'
    file_path.write_text(
        'PMID- 11111111\n'
        'TI  - Sickle Cell Disease.\n'
        'AB  - Sickle cell disease is a hemoglobinopathy.\n'
        'FAU - Rees, David C\n'
        'AU  - Rees DC\n'
        'MH  - Acute Chest Syndrome/etiology/therapy\n'
        'MH  - Anemia, Sickle Cell/complications\n'
        'DP  - 2017 Apr 20\n',
        encoding='utf-8',
    )

    service = ExtractionService()
    metadata = service.extract_metadata(file_path)

    assert metadata['title'] == 'Sickle Cell Disease'
    assert metadata['authors'] == ['Rees, David C']
    assert metadata['keywords'] == ['Acute Chest Syndrome/etiology/therapy', 'Anemia, Sickle Cell/complications']
    assert metadata['publication_year'] == 2017


def test_extract_metadata_falls_back_to_au_when_fau_missing(tmp_path: Path) -> None:
    file_path = tmp_path / 'pubmed-22222222.txt'
    file_path.write_text(
        'PMID- 22222222\n'
        'TI  - A Study Without Full Author Names.\n'
        'AU  - Rees DC\n'
        'DP  - 2015\n',
        encoding='utf-8',
    )

    service = ExtractionService()
    metadata = service.extract_metadata(file_path)

    assert metadata['authors'] == ['Rees DC']


def test_extract_metadata_handles_missing_dp(tmp_path: Path) -> None:
    file_path = tmp_path / 'pubmed-33333333.txt'
    file_path.write_text(
        'PMID- 33333333\n'
        'TI  - A Study With No Publication Date.\n',
        encoding='utf-8',
    )

    service = ExtractionService()
    metadata = service.extract_metadata(file_path)

    assert metadata['publication_year'] is None


def test_extract_metadata_dp_year_only(tmp_path: Path) -> None:
    file_path = tmp_path / 'pubmed-44444444.txt'
    file_path.write_text(
        'PMID- 44444444\n'
        'TI  - A Study With Year-Only Publication Date.\n'
        'DP  - 2010\n',
        encoding='utf-8',
    )

    service = ExtractionService()
    metadata = service.extract_metadata(file_path)

    assert metadata['publication_year'] == 2010


def test_extract_metadata_degenerate_medline_record_has_no_crash(tmp_path: Path) -> None:
    file_path = tmp_path / 'pubmed-55555555.txt'
    file_path.write_text('PMID- 55555555\n', encoding='utf-8')

    service = ExtractionService()
    metadata = service.extract_metadata(file_path)

    assert metadata['title'] is None
    assert metadata['authors'] == []
    assert metadata['keywords'] == []
    assert metadata['publication_year'] is None
