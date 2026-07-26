from pathlib import Path

from app.config_util import Settings


def test_collection_config_overrides_base_values(tmp_path: Path) -> None:
    config_dir = tmp_path / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'application.yaml').write_text(
        'default:\n  collection_name: default\n  chunk_size: 400\n', encoding='utf-8'
    )
    (config_dir / 'collections.yaml').write_text('cancer:\n  chunk_size: 800\n  vector_table_name: cancer_chunks\n', encoding='utf-8')

    settings = Settings.from_yaml(collection_name='cancer', config_dir=str(config_dir))

    assert settings.collection_name == 'cancer'
    assert settings.chunk_size == 800
    assert settings.vector_table_name == 'cancer_chunks'


def test_environment_overrides_apply_on_top_of_default(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'application.yaml').write_text(
        'default:\n  debug: false\n  chunk_size: 400\n'
        'environments:\n  prod:\n    debug: false\n  local:\n    debug: true\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('APP_ENV', 'local')
    local_settings = Settings.from_yaml(config_dir=str(config_dir))
    assert local_settings.debug is True
    assert local_settings.chunk_size == 400

    monkeypatch.setenv('APP_ENV', 'prod')
    prod_settings = Settings.from_yaml(config_dir=str(config_dir))
    assert prod_settings.debug is False


def test_unknown_collection_falls_back_to_base_values(tmp_path: Path) -> None:
    config_dir = tmp_path / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'application.yaml').write_text('default:\n  chunk_size: 400\n', encoding='utf-8')
    (config_dir / 'collections.yaml').write_text('cancer:\n  chunk_size: 800\n', encoding='utf-8')

    settings = Settings.from_yaml(collection_name='nonexistent', config_dir=str(config_dir))

    assert settings.collection_name == 'nonexistent'
    assert settings.chunk_size == 400


def test_sickle_cell_collection_settings_are_loaded() -> None:
    settings = Settings.from_yaml(collection_name='sickle_cell', config_dir='configs')

    assert settings.collection_name == 'sickle_cell'
    assert settings.chunk_size == 600
    assert settings.chunk_overlap == 120
    assert settings.retrieval_top_k == 5
    # vector_table_name is no longer set per-collection: every collection shares
    # one table (document_chunks) and is distinguished by the collection column.
    assert settings.vector_table_name == 'document_chunks'
