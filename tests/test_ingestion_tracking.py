from app.application.services.ingestion_tracking import IncrementalProcessingService, IngestionStatusService


def test_checksum_is_stable_and_documents_can_be_skipped(tmp_path) -> None:
    file_path = tmp_path / 'paper.txt'
    file_path.write_text('Some content for checksum testing.', encoding='utf-8')

    service = IncrementalProcessingService()
    checksum = service.compute_checksum(str(file_path))
    assert checksum

    skipped_on_first_run = service.should_skip(str(file_path), checksum)
    assert skipped_on_first_run is False

    service.mark_processed(str(file_path), checksum)
    skipped_on_second_run = service.should_skip(str(file_path), checksum)
    assert skipped_on_second_run is True

    changed = service.should_skip(str(file_path), 'different-checksum')
    assert changed is False


def test_status_service_tracks_progress_and_failure() -> None:
    service = IngestionStatusService()

    service.mark_started('doc-1', 'bronze')
    service.mark_completed('doc-1', 'bronze')
    service.mark_failed('doc-1', 'silver', 'bad input')

    status = service.get_status('doc-1')

    assert status['bronze'] == 'completed'
    assert status['silver'] == 'failed'
    assert status['silver_error'] == 'bad input'


def test_status_service_reports_overall_progress_summary() -> None:
    service = IngestionStatusService()

    service.mark_completed('doc-2', 'bronze')
    service.mark_completed('doc-2', 'silver')
    service.mark_completed('doc-2', 'gold')

    summary = service.get_summary('doc-2')

    assert summary['overall'] == 'completed'
    assert summary['completed_stages'] == 3
    assert summary['total_stages'] == 3
