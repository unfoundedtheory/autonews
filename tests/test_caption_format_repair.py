"""Caption formatting must never invent unsupported facts."""
from types import SimpleNamespace
import json
import pytest
from utbot.caption_format import normalize_generated_caption, DraftFormatError
from utbot.pipeline import author_from_source, normalize

CAPTION = ("Ketika teleskop diarahkan ke angkasa, tim melihat pola yang sulit dijelaskan.\n"
           "Peneliti NASA mencatat sinyal melalui instrumen mereka.\n"
           "Namun hasil itu masih harus diuji untuk membedakan sinyal dan gangguan.\n"
           "Apa yang akan ditemukan tim pada pemeriksaan berikutnya.")
SOURCE=normalize(("Scientists studied observations from a distant telescope array. "
                  "They said additional measurements are required before any discovery claim. ")*10)


def test_single_newlines_become_real_paragraphs():
    clean,tags,repairs=normalize_generated_caption("Caption:\n"+CAPTION+"\n#NASA #Sains #Riset #Astronomi #UnfoundedTheory")
    assert clean.count("\n\n")==3
    assert clean.endswith("?")
    assert len(tags)==5
    assert "restored_paragraph_separators" in repairs


def test_facts_and_assertions_never_get_rewritten():
    caption="Para ilmuwan telah merilis laporan. Tidak ada pengukuran baru yang dikonfirmasi."
    clean,tags,repairs=normalize_generated_caption(caption)
    assert clean==caption and tags==[]
    assert "?" not in clean


def test_only_question_opening_ends_with_question_mark():
    caption=CAPTION[:-1]+"."
    clean,_,repairs=normalize_generated_caption(caption)
    assert clean.endswith("?")
    assert "question_punctuation" in repairs


def test_writer_preserves_valid_source_evidence_and_corrects_layout():
    story=SimpleNamespace(title="Telescope science",source_url="https://science.nasa.gov/test",
                          published_at=None,topic="astronomy")
    def fake_writer(query):
        assert isinstance(json.loads(query),dict)
        return {
            "highlight":"Fisikawan Temukan Sinyal Aneh Dalam Pencarian Partikel Dark Matter",
            "caption":CAPTION+"\n#NASA #Sains #Riset #Astronomi #UnfoundedTheory",
            "hashtags":["#NASA","#Sains","#Riset","#Astronomi","#UnfoundedTheory"],
            "evidence":[
                {"claim":"observasi","quote":"Scientists studied observations from a distant telescope array."},
                {"claim":"butuh pengujian","quote":"They said additional measurements are required before any discovery claim."}
            ]
        }
    data,evidence=author_from_source(story,SOURCE,llm=fake_writer)
    assert data["caption"].count("\n\n")==3
    assert len(evidence)==2 and all(x["evidence_checked"] for x in evidence)


def test_structured_codes_are_not_raw_model_responses():
    error=DraftFormatError(["caption_paragraph_count","ending_not_question"])
    assert error.issue_codes==("caption_paragraph_count","ending_not_question")
