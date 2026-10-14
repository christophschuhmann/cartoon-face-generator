"""Synthetic unit fixtures test aggregation; they are never recognition evidence."""
import json
import pytest
from cartoon_face.emotion_library import catalog
from cartoon_face.emotion_reviews import evaluate_reviews


def write_fixture(tmp_path,rows,method='manual viewer judgments'):
    path=tmp_path/'reviews.json'
    path.write_text(json.dumps({'taxonomy_id':catalog()['taxonomy_id'],'method':method,'reviews':rows}))
    return path


def test_review_confusion_matrix_handles_unclear_and_missing_categories(tmp_path):
    path=write_fixture(tmp_path,[
      {'target_slug':'anger','recognized_slug':'anger','confidence':4,'target_name_hidden_when_rated':True},
      {'target_slug':'anger','recognized_slug':'unclear','confidence':1},
      {'target_slug':'sadness','recognized_slug':'disappointment','confidence':2,'target_name_hidden_when_rated':True}])
    report=evaluate_reviews([path],tmp_path/'result.json')
    assert report['target_agreement_rate']==pytest.approx(1/3)
    assert report['hidden_target_agreement_rate']==.5
    assert report['per_category']['fear']['target_agreement_rate'] is None
    assert report['confusion_matrix']['counts'][31][40]==1
    assert (tmp_path/'result.csv').exists()


def test_automated_or_empty_exports_are_not_human_evidence(tmp_path):
    with pytest.raises(ValueError,match='automated'):
        evaluate_reviews([write_fixture(tmp_path,[],method='automated UI smoke-test example')])
    with pytest.raises(ValueError,match='No completed'):
        evaluate_reviews([write_fixture(tmp_path,[])])


def test_review_rejects_unknown_labels(tmp_path):
    path=write_fixture(tmp_path,[{'target_slug':'anger','recognized_slug':'not_a_category','confidence':3}])
    with pytest.raises(ValueError,match='unknown'):evaluate_reviews([path])
