"""Display-only v1.7.28 reference/editorial QA without grader or cache mutation."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import sys
import types
from pathlib import Path
import pytest

fake_ollama = types.ModuleType('ollama')
class DummyClient:
    def __init__(self, *args, **kwargs): pass
    def list(self): return {'models': []}
fake_ollama.Client = DummyClient
fake_ollama.chat = lambda *args, **kwargs: {'message': {'content': '{}'}}
sys.modules.setdefault('ollama', fake_ollama)
from backend import main as m

FILE = Path(m.__file__).with_name('quiz_reference_editorial_v1728.json')
ROWS = json.loads(FILE.read_text(encoding='utf-8'))['entries']


def base_result(reference='元の参照訳', note='', feedback='原文の主要な意味単位は訳文に保持されています。'):
    return {
        'score': 100, 'verdict': 'correct',
        'reference_translation': reference, 'feedback': feedback,
        'score_breakdown': {'meaning':70,'terminology':15,'japanese':15,'raw_total':100,'total':100,'cap_reason':''},
        'japanese_quality': {'level':'natural','note':''},
        'issues': [], 'key_points': [], 'external_audit': {'status':'local_only'},
        'semantic_units': [{
            'id': 'u1','source':'The measured values agreed.',
            'translation':'測定値が一致した','importance':'core',
            'status':'correct','evidence_span':'測定値が一致した','note': note,
        }],
    }


def test_stable_grader_identity_and_new_quality_layer():
    assert m.QUIZ_GRADER_VERSION == 'quiz-grader-v1.7.27'
    assert m.read_root()['quiz_revision'] == 'v1.7.27-source-anchored-science-and-japanese-fluency'
    assert m.read_root()['reference_quality_revision'] == 'v1.7.28-display-only'
    assert m._quiz_rubric_cache_path().name == 'quiz_rubric_cache_v10.json'
    assert m.QUIZ_EVALUATION_CACHE_PATH.name == 'quiz_evaluation_cache_v1.json'


def test_editorial_records_are_sha_locked_and_source_unique():
    assert len(ROWS) == 5
    seen = set()
    for row in ROWS:
        source = re.sub(r'\s+',' ',row['source_text']).strip()
        assert hashlib.sha256(source.encode()).hexdigest() == row['source_sha256']
        assert row['source_sha256'] not in seen
        seen.add(row['source_sha256'])
        assert row['observed_reference'] != row['reviewed_reference']
        assert row['review_status'] == 'editorially_reviewed_not_user_approved'
    assert len(m._quiz_reference_editorial_records()) == 5


@pytest.mark.parametrize('row',ROWS,ids=lambda r:r['id'])
def test_five_source_scoped_reference_repairs_never_modify_grading(row):
    original=base_result(reference=row['observed_reference'])
    backup=copy.deepcopy(original)
    after=m._quiz_quality_api_payload(row['source_text'],'測定値が一致した',original)
    assert after['reference_translation'] == row['reviewed_reference']
    assert after['reference_review']['status'] == 'editorially_reviewed'
    assert after['reference_review']['review_id'] == row['id']
    assert after['reference_review']['cache_untouched'] is True
    assert not after['reference_review']['flags']
    assert original == backup
    for name in ('score','verdict','score_breakdown','issues','japanese_quality','key_points','external_audit'):
        assert original[name] == after[name]
    assert m._quiz_quality_api_payload(row['source_text'],'測定値が一致した',after)['reference_translation'] == after['reference_translation']


def test_only_exact_source_and_exact_observed_translation_can_autorepair():
    row=ROWS[0]
    wrong_source=m._quiz_quality_api_payload(row['source_text']+' EXTRA','',base_result(row['observed_reference']))
    assert wrong_source['reference_translation'] == row['observed_reference']
    assert wrong_source['reference_review']['status'] == 'unchecked' or wrong_source['reference_review']['status'] == 'needs_review'
    changed_ref=m._quiz_quality_api_payload(row['source_text'],'',base_result('別の編集者が変更した訳'))
    assert changed_ref['reference_translation'] == '別の編集者が変更した訳'
    assert changed_ref['reference_review']['status'] == 'needs_review'
    assert changed_ref['reference_review']['flags']


@pytest.mark.parametrize('source,translation',[
    ('A new undulator was developed.','アンジュレーターを開発した。'),
    ('Impregnation should be done later.','浸透を後で行う。'),
    ('The current adjusts the field.','その積分が決定するアンジュレータ内の軌道を決める。'),
    ('The method is required.','必要となることが必要である。'),
    ('There are two hard X-ray lines and a soft X-ray line.','硬X線の2本と軟X線SASE3がある。'),
])
def test_unknown_reference_risks_are_warned_not_autocorrected(source,translation):
    after=m._quiz_quality_api_payload(source,'',base_result(translation))
    assert after['reference_translation'] == translation
    assert after['reference_review']['status'] == 'needs_review'
    assert after['reference_review']['flags']


@pytest.mark.parametrize('source,translation',[
    ('A new undulator was developed.','アンジュレータを開発した。'),
    ('Impregnation should be done later.','含浸を後で行う。'),
    ('The method is required.','この方法が必要である。'),
])
def test_proper_scientific_reference_is_not_warned(source,translation):
    after=m._quiz_quality_api_payload(source,'',base_result(translation))
    assert after['reference_review']['status']=='unchecked'
    assert after['reference_review']['flags']==[]


def test_note_repair_only_for_old_rescue_marker_and_correct_status():
    old=m._QUIZ_OLD_CONTACT_RESCUE_NOTE
    result=base_result(note=old)
    after=m._quiz_quality_api_payload('A model performed very well.','測定値が一致した',result)
    assert '接触関係' not in after['semantic_units'][0]['note']
    assert result['semantic_units'][0]['note']==old
    contact=base_result(note=old)
    contact['semantic_units'][0]['source']='where the tape touches the body'
    contact['semantic_units'][0]['evidence_span']='テープが治具に接触'
    actual=m._quiz_quality_api_payload('where the tape touches the body','テープが治具に接触',contact)
    assert '接触関係' in actual['semantic_units'][0]['note']
    for status in ('wrong','partial','missing'):
        unsafe=base_result(note=old)
        unsafe['semantic_units'][0]['status']=status
        changed=m._quiz_quality_api_payload('A model performed very well.','',unsafe)
        assert changed['semantic_units'][0]['note']==old


def test_generic_feedback_has_a_verbatim_learner_span_if_available():
    before=base_result()
    answer='測定値が一致した。'
    after=m._quiz_quality_api_payload('The measured values agreed.',answer,before)
    assert '「The measured values agreed.」' in after['feedback']
    assert '「測定値が一致した」' in after['feedback']
    assert '対応' in after['feedback']
    assert before['feedback'] in m._QUIZ_GENERIC_CORRECT_FEEDBACK


def test_generic_feedback_no_span_does_not_invent_evidence():
    before=base_result()
    before['semantic_units'][0]['evidence_span']=''
    after=m._quiz_quality_api_payload('The measured values agreed.','無関係な文章',before)
    assert '訳文の「' not in after['feedback']
    assert '正しいと判定' in after['feedback']


def test_never_turn_bad_translation_into_positive_feedback():
    result=base_result()
    result['semantic_units'][0]['status']='missing'
    after=m._quiz_quality_api_payload('The measured values agreed.','',result)
    assert after['feedback']==result['feedback']
    result=base_result()
    result['issues']=[{'category':'mistranslation','message':'符号反転'}]
    after=m._quiz_quality_api_payload('The measured values agreed.','',result)
    assert after['feedback']==result['feedback']


def test_non_generic_feedback_remains_word_for_word():
    result=base_result(feedback='主要な物理条件1 Ω·mが抜けています。')
    after=m._quiz_quality_api_payload('The measured values agreed.','',result)
    assert after['feedback']==result['feedback']


def test_cached_api_only_presentational_and_preserves_existing_cache(monkeypatch):
    row=ROWS[0]
    original=base_result(row['observed_reference'])
    backup=copy.deepcopy(original)
    monkeypatch.setattr(m,'_get_cached_quiz_evaluation',lambda *args:{'evaluation':original,'created_at':'old'})
    monkeypatch.setattr(m,'_quiz_vocabulary_candidates',lambda *_:[])
    monkeypatch.setattr(m,'_store_quiz_evaluation',lambda *args: pytest.fail('must not update stored cached eval'))
    response=m.check_translation(m.TranslationRequest(source_text=row['source_text'],user_answer='任意の回答'))
    assert response['cache_hit'] is True
    assert response['evaluation']['reference_translation']==row['reviewed_reference']
    assert original==backup


def test_quality_overlay_is_safe_if_registry_missing(monkeypatch):
    monkeypatch.setattr(m,'_QUIZ_REFERENCE_REVIEW_FILE', Path('/tmp/this_should_not_exist_v1728.json'))
    row=ROWS[0]
    candidate=m._quiz_quality_api_payload(row['source_text'],'',base_result(row['observed_reference']))
    assert candidate['reference_translation']==row['observed_reference']
    assert candidate['reference_review']['status'] in ('needs_review','unchecked')
