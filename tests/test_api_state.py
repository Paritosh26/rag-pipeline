from app.presentation.api import resolve_services


def test_resolve_services_reuses_collection_state() -> None:
    app_state = {'services_by_collection': {}}

    first = resolve_services('sickle_cell', app_state)
    second = resolve_services('sickle_cell', app_state)

    assert first is second
    assert first.retrieval.vector_store is second.retrieval.vector_store
