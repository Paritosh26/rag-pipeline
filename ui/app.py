"""Lightweight Streamlit client for manually testing the biomedical RAG API.

Runs in its own virtual environment (../.venv-ui) so its dependency tree
(pandas, pyarrow, altair, ...) never touches the lean FastAPI backend's venv.
This is a thin HTTP client only -- all business logic stays in the API.
"""
from __future__ import annotations

from pathlib import Path

import requests
import streamlit as st
import yaml

COLLECTIONS_PATH = Path(__file__).resolve().parents[1] / 'configs' / 'collections.yaml'


def post_json(base_url: str, endpoint: str, payload: dict, timeout: int) -> dict:
    """POST a JSON payload to the API and return the decoded response."""
    response = requests.post(f'{base_url}{endpoint}', json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title='Biomedical RAG', page_icon='🧬', layout='centered')
st.title('🧬 Biomedical RAG')

if 'base_url' not in st.session_state:
    st.session_state.base_url = 'http://localhost:8000'

with st.sidebar:
    st.header('Connection')
    base_url = st.text_input('API base URL', value=st.session_state.base_url).rstrip('/')
    st.session_state.base_url = base_url

    try:
        health = requests.get(f'{base_url}/health', timeout=3)
        st.success('API reachable') if health.ok else st.error(f'API returned {health.status_code}')
    except requests.exceptions.RequestException as exc:
        st.error(f'API unreachable: {exc}')

    st.header('Collection')
    if COLLECTIONS_PATH.exists():
        all_collections = yaml.safe_load(COLLECTIONS_PATH.read_text(encoding='utf-8')) or {}
        collections = sorted(all_collections.keys())
    else:
        collections = []
    collections = collections or ['default']
    # Default to sickle_cell (the collection with real ingested data) rather than
    # whichever name happens to sort first alphabetically.
    default_index = collections.index('sickle_cell') if 'sickle_cell' in collections else 0
    collection = st.selectbox('Disease collection', options=collections, index=default_index)

    st.header('Ingest')
    folder_path = st.text_input('Folder path', value=f'data/raw/{collection}')
    if st.button('Ingest folder'):
        try:
            result = post_json(
                base_url,
                '/ingest-folder',
                {'folder_path': folder_path, 'collection': collection},
                timeout=120,
            )
            st.success(result)
        except requests.exceptions.RequestException as exc:
            st.error(f'Ingestion failed: {exc}')

st.subheader('Ask a question')
question = st.text_area('Question', placeholder='What are the main clinical complications of sickle cell disease?')

if st.button('Ask', type='primary') and question.strip():
    try:
        payload = post_json(
            st.session_state.base_url,
            '/query',
            {'question': question, 'collection': collection},
            timeout=60,
        )
    except requests.exceptions.RequestException as exc:
        st.error(f'Query failed: {exc}')
    else:
        st.markdown('### Answer')
        st.write(payload['answer'])

        st.markdown(f"### Citations ({len(payload['citations'])})")
        for i, citation in enumerate(payload['citations'], start=1):
            with st.expander(f"{i}. {citation['source_id']}  —  score {citation['score']:.3f}"):
                st.write(citation['excerpt'])
                st.json(citation['metadata'])

        st.caption(
            f"Collection: {payload['lineage']['collection']} · "
            f"Retrieved chunks: {payload['lineage']['retrieved_chunk_count']}"
        )
