"""Stronger training-only augmentations; the frozen v2 evaluation stays untouched.

Perspective and two-stage elastic shear transform pixels and labels identically.
Profiles mix clear views with stronger camera/domain shifts instead of making
every example maximally damaged. All randomness is explicit in the descriptor.
"""
import copy
import cv2
import numpy as np
from PIL import Image
from cartoon_face.augmentation import (
    sample_transform, transform_coordinates, transform_image, flip_permutation,
)

VERSION = 'training_raster_aug_v3'


def sample_training_transform(size, seed, profile='strong', strength=1.):
    if profile not in ('mild', 'strong', 'robust', 'curriculum'):
        raise ValueError('Unknown training augmentation profile')
    if not 0 <= strength <= 1:
        raise ValueError('Strength must be in [0,1]')
    rng = np.random.default_rng(seed)
    draw = rng.random()
    # Clear views and original mild transforms preserve accurate ordinary poses.
    if profile == 'mild' or draw < .30:
        descriptor = sample_transform(size, size, int(seed), draw >= .08)
        descriptor['training_profile'] = profile
        return descriptor
    w, h = size
    hard = profile == 'robust' and draw > .85
    magnitude = strength * (1.25 if hard else 1.)
    fit = rng.uniform(1 - .24*magnitude, 1.)
    letter = np.array([[fit, 0, (w-w*fit)/2],
                       [0, fit, rng.uniform(.08, .75)*(h-h*fit)], [0, 0, 1.]])
    angle = np.deg2rad(rng.uniform(-25, 25)*magnitude)
    scale = rng.uniform(1-.24*magnitude, 1+.16*magnitude)
    sx, sy = scale*rng.uniform(1-.18*magnitude, 1+.18*magnitude, 2)
    linear = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]) @ np.diag([sx, sy])
    center = np.array([w/2, h/2])
    affine = np.eye(3)
    affine[:2, :2] = linear
    affine[:2, 2] = center-linear@center+rng.uniform([-w*.09, -h*.09], [w*.09, h*.09])*magnitude
    flip = bool(rng.random() < .4)
    if flip:
        affine = np.array([[-1., 0, w-1], [0, 1, 0], [0, 0, 1.]]) @ affine
    corners = np.array([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]], dtype=np.float32)
    displaced = corners + (rng.uniform(-1, 1, (4, 2))*[w*.035, h*.05]*magnitude).astype(np.float32)
    perspective = cv2.getPerspectiveTransform(corners, displaced)
    descriptor = sample_transform(size, size, int(seed), False)
    descriptor.update(version=VERSION, augmented=True, training_profile=profile,
                      strength=float(strength), hard=hard, homography=(perspective@affine@letter).tolist(),
                      horizontal_flip=flip, label_permutation=flip_permutation().tolist() if flip else list(range(101)))
    descriptor['elastic'] = {'ax':float(rng.uniform(-.035, .035)*w*magnitude),
        'ay':float(rng.uniform(-.045, .045)*h*magnitude),
        'phase_x':float(rng.uniform(0, 2*np.pi)), 'phase_y':float(rng.uniform(0, 2*np.pi))}
    background = rng.uniform(150, 255, 3)
    ink = rng.uniform(0, 65, 3)
    if rng.random() < .16:
        background, ink = ink, background
    descriptor['appearance'] = {'background':background.tolist(), 'ink':ink.tolist(),
        'gradient_x':float(rng.uniform(-30,30)), 'gradient_y':float(rng.uniform(-30,30)),
        'noise_sigma':float(rng.uniform(.5, 12 if hard else 9)), 'noise_seed':int(rng.integers(2**32)),
        'blur_sigma':float(rng.uniform(.2, 1.15 if hard else .9)) if rng.random() < .5 else 0.,
        'low_resolution_scale':float(rng.uniform(.35 if hard else .45, 1)) if rng.random() < .45 else 1.,
        'jpeg_quality':int(rng.integers(30 if hard else 40, 98)) if rng.random() < .7 else None}
    descriptor['ink_morph'] = float(rng.choice([-1., 1.])*rng.uniform(.12, .38)) if rng.random() < .25 else 0.
    descriptor['occluders'] = []
    if rng.random() < .2:
        pw, ph = rng.uniform(.05,.16)*w, rng.uniform(.06,.19)*h
        x, y = rng.uniform(.1*w, .85*w-pw), rng.uniform(.15*h, .85*h-ph)
        descriptor['occluders'] = [[int(x), int(y), int(x+pw), int(y+ph)]]
    return descriptor


def _after_projection(descriptor):
    rest = copy.deepcopy(descriptor)
    rest['affine'] = [[1., 0., 0.], [0., 1., 0.]]
    return rest


def training_coordinates(coords, descriptor):
    if 'homography' not in descriptor:
        return transform_coordinates(coords, descriptor)
    q = np.column_stack([coords, np.ones(len(coords))]) @ np.asarray(descriptor['homography']).T
    q = q[:, :2]/q[:, 2:]
    return transform_coordinates(q, _after_projection(descriptor))


def training_image(image, descriptor):
    if 'homography' not in descriptor:
        return transform_image(image, descriptor)
    w, h = descriptor['target_size']
    gray = cv2.warpPerspective(np.asarray(image.convert('L')), np.asarray(descriptor['homography']),
                              (w,h), flags=cv2.INTER_LINEAR, borderValue=255)
    amount = descriptor.get('ink_morph', 0.)
    if amount:
        kernel = np.ones((3,3), dtype=np.uint8)
        changed = cv2.erode(gray,kernel) if amount > 0 else cv2.dilate(gray,kernel)
        gray = np.rint((1-abs(amount))*gray+abs(amount)*changed).astype(np.uint8)
    return transform_image(Image.fromarray(gray), _after_projection(descriptor))
