import copy
import numpy as np
import pytest
from PIL import Image
from cartoon_face.augmentation import flip_permutation,sample_transform,transform_coordinates,inverse_elastic,transform_image,augment_raster,annotation_for_pose
from cartoon_face.social_expressions import social_pose
from cartoon_face.model import topology,landmark_arrays


def test_flip_swaps_all_anatomical_ids_and_visibility_and_is_an_involution():
    permutation=flip_permutation();assert np.array_equal(permutation[permutation],np.arange(101))
    p=social_pose('knowing_wink');d=sample_transform((1450,750),(1450,750),1,False)
    d.update(horizontal_flip=True,label_permutation=permutation.tolist(),affine=[[-1,0,1449],[0,1,0]])
    ann=annotation_for_pose(p,d);old,v=landmark_arrays(p,pixels=True)
    assert np.allclose(np.array(ann['xy_pixels'])[:,0],1449-old[permutation,0])
    assert ann['source_visibility']==v[permutation].tolist()


def test_elastic_image_inverse_exactly_inverts_the_label_forward_map():
    d=sample_transform((320,192),(320,192),42,False)
    d['elastic']={'ax':6.,'ay':4.,'phase_x':.3,'phase_y':1.1}
    q=np.random.default_rng(1).uniform([0,0],[320,192],(101,2))
    assert np.allclose(inverse_elastic(transform_coordinates(q,d),d),q,atol=1e-10)


def test_bright_landmark_pixels_follow_the_same_affine_and_elastic_map():
    image=Image.new('L',(320,192),255);a=np.array(image);q=np.array([[130.,83.]])
    a[80:87,127:134]=0;d=sample_transform((320,192),(320,192),1,False)
    d['affine']=[[.95,.08,7.],[-.05,1.01,5.]];d['elastic']={'ax':4.,'ay':3.,'phase_x':.4,'phase_y':1.2}
    d['label_permutation']=[0]
    warped=np.array(transform_image(Image.fromarray(a),d).convert('L'));yy,xx=np.nonzero(warped<50)
    expected=transform_coordinates(q,d)[0]
    assert np.linalg.norm(np.array([xx.mean(),yy.mean()])-expected)<1


def test_random_appearance_is_colored_reproducible_and_preserves_all_labels():
    p=social_pose('mock_monster');im,a=augment_raster(p,314,384,384)
    other,b=augment_raster(p,314,384,384)
    assert np.array_equal(np.array(im),np.array(other)) and a==b
    assert len(a['xy_pixels'])==len(a['visibility'])==101
    assert a['keypoint_ids']==list(range(101))
    assert not np.array_equal(np.array(im)[:,:,0],np.array(im)[:,:,1])


def test_outside_coordinates_are_retained_and_masked_instead_of_clamped():
    p=social_pose('knowing_wink');d=sample_transform((1450,750),(384,200),1,False);d['affine'][0][2]-=500
    ann=annotation_for_pose(p,d)
    assert any(q[0]<0 for q in ann['xy_pixels']) and not any(ann['in_frame'])
    assert not any(ann['regression_mask']) and not any(ann['visibility'])
