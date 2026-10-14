import copy
import numpy as np
from PIL import Image
from training.augmentation import sample_training_transform,training_image,training_coordinates
from cartoon_face.augmentation import inverse_elastic


def strong_descriptor():
    for seed in range(100):
        descriptor=sample_training_transform((320,192),seed,'robust')
        if 'homography' in descriptor:
            return descriptor
    raise AssertionError('No strong profile sampled')


def test_perspective_and_shear_share_an_exact_label_forward_inverse():
    descriptor=strong_descriptor();descriptor['label_permutation']=list(range(101))
    points=np.random.default_rng(42).uniform([20,20],[300,170],(101,2))
    warped=training_coordinates(points,descriptor)
    unsheared=inverse_elastic(warped,descriptor)
    q=np.column_stack([unsheared,np.ones(101)])@np.linalg.inv(descriptor['homography']).T
    assert np.allclose(q[:,:2]/q[:,2:],points,atol=1e-9)


def test_projected_dark_marker_tracks_label_even_with_elastic_warp():
    descriptor=strong_descriptor();descriptor['label_permutation']=[0]
    descriptor['ink_morph']=0.;descriptor['occluders']=[]
    descriptor['appearance'].update(background=[255]*3,ink=[0]*3,noise_sigma=0,blur_sigma=0,
        low_resolution_scale=1.,jpeg_quality=None,gradient_x=0,gradient_y=0)
    source=np.full((192,320),255,dtype=np.uint8);source[87:94,147:154]=0
    image=np.asarray(training_image(Image.fromarray(source),descriptor).convert('L'))
    y,x=np.nonzero(image<100)
    expected=training_coordinates(np.array([[150.,90.]]),descriptor)[0]
    assert len(x)>5
    assert np.linalg.norm(np.array([x.mean(),y.mean()])-expected)<1.


def test_stronger_augments_are_reproducible_have_finite_labels_and_keep_clean_views():
    source=Image.fromarray(np.random.default_rng(3).integers(0,256,(192,320),dtype=np.uint8))
    q=np.random.default_rng(7).uniform([0,0],[320,192],(101,2))
    clean_count=strong_count=0
    for seed in range(100):
        d=sample_training_transform((320,192),seed,'strong')
        assert d==sample_training_transform((320,192),seed,'strong')
        assert np.isfinite(training_coordinates(q,d)).all()
        assert training_coordinates(q,d).shape==(101,2)
        assert training_image(source,d).size==(320,192)
        strong_count+='homography' in d;clean_count+=not d['augmented']
    assert strong_count>5 and clean_count>0
