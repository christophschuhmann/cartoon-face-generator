import copy,json
import numpy as np
import pytest
from cartoon_face.model import topology,landmark_arrays,validate_pose,inside_nonzero_polygon
from cartoon_face.social_expressions import social_catalog,social_pose,social_cue_checks
from cartoon_face.large_dataset import categories,sample_pose,extreme_jitter,_worker,iter_records
from cartoon_face.emotion_library import emotion_pose40
from cartoon_face.renderer import render_svg
from cartoon_face.animation import interpolate_pose


@pytest.mark.parametrize('profile',social_catalog()['profiles'],ids=lambda p:p['slug'])
def test_every_social_recipe_preserves_the_fixed_rig_and_protected_cues(profile):
    p=social_pose(profile['slug'],42,.95);validate_pose(p)
    assert social_cue_checks(p)['passed']
    assert len(p['keypoints'])==101 and len(p['expression']['weights'])==60
    assert 'emotion' not in p and sum(p['expression']['weights'])==1
    assert render_svg(p)==render_svg(social_pose(profile['slug'],42,.95))


def test_every_ood_axis_really_moves_five_to_ten_percent_including_absent_points():
    source=social_pose('knowing_wink',42);p=extreme_jitter(source,17)
    delta=landmark_arrays(p)[0]-landmark_arrays(source)[0]
    assert np.all(np.abs(delta)>=.05-1e-12) and np.all(np.abs(delta)<=.1+1e-12)
    assert np.allclose(delta,p['recipe']['ood_jitter']['actual_delta'])
    assert 'emotion' not in p and 'expression' not in p
    assert p['provenance']['source_target']['slug']=='knowing_wink'


def test_nonzero_clipping_matches_svg_for_twice_wound_ood_polygons():
    outline=[[0,0],[3,0],[3,3],[0,3],[0,0],[3,0],[3,3],[0,3]]
    assert inside_nonzero_polygon(outline,[1,1])
    assert not inside_nonzero_polygon(outline,[4,1])


def test_geometric_bounds_fit_shrinks_before_translation_in_the_previous_elation_edge_case():
    category=next(p for p in categories() if p['slug']=='elation')
    # Strong high brows + latent tongue/chin can jointly span more than the frame.
    for index in (0,47,78,159,355,527,884,999):
        p,_=sample_pose(category,index);q,_=landmark_arrays(p)
        assert q.min()>=.0059 and q.max()<=.9941
        assert len({k['id'] for k in p['keypoints'].values()})==101


def test_shards_are_deterministic_replayable_and_resumable(tmp_path):
    category=categories()[40];report=_worker((category,3,42,str(tmp_path),False))
    (tmp_path/'manifest.json').write_text(json.dumps({'shards':report['shards']}))
    rows=list(iter_records(tmp_path));assert len(rows)==3
    for key,svg,p in rows:
        assert key==p['dataset']['sample_id'] and render_svg(p)==svg
        assert p['dataset']['target']['kind']=='social'
    assert _worker((category,3,42,str(tmp_path),False))==report
    other=tmp_path/'other';second=_worker((category,3,42,str(other),False))
    assert [r['sha256'] for r in report['shards']]==[r['sha256'] for r in second['shards']]
    shard=tmp_path/report['shards'][0]['file'];data=bytearray(shard.read_bytes());data[-1]^=1;shard.write_bytes(data)
    with pytest.raises(ValueError):_worker((category,3,42,str(tmp_path),False))


def test_mixed_social_labels_do_not_silently_keep_the_first_category():
    a=social_pose('knowing_wink');b=social_pose('offended');p=interpolate_pose(a,b,.3)
    assert p['expression']['category_id'] is None
    assert p['expression']['weights'][0]==pytest.approx(.7) and p['expression']['weights'][21]==pytest.approx(.3)
    mixed=interpolate_pose(emotion_pose40('anger'),b,.4)
    assert sum(mixed['emotion']['weights'])==pytest.approx(.6) and sum(mixed['expression']['weights'])==pytest.approx(.4)
