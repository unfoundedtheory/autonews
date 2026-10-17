"""Malformed writer output is recoverable, never an AttributeError."""
import pytest
from utbot.pipeline import check_evidence, author_from_source
from types import SimpleNamespace


def test_string_evidence_reports_repairable_validation_error():
    with pytest.raises(ValueError,match='evidence wajib berupa object'):
        check_evidence({'evidence':['Kutipan bukan JSON object','another quote']},
                       'https://science.nasa.gov/test','x'*400)


def test_writer_response_string_is_clean_validation_error():
    story=SimpleNamespace(title='Observasi',source_url='https://science.nasa.gov/test',
                          published_at=None,topic='astronomy')
    with pytest.raises(ValueError,match='JSON object'):
        author_from_source(story,'Test '*100,llm=lambda query:'invalid result')
