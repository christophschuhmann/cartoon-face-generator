"""Conservative tongue-protrusion heuristic, not a MediaPipe blendshape.

Looks for a connected pink/red shape extending beyond the lower lip, relative
to nearby skin. Rotates a small mouth crop; never retains input images.
"""
import math
import numpy as np
import cv2


def tongue_protrusion(rgb, landmarks, jaw_open=0.0, blendshapes=None):
    if len(landmarks) < 468:
        return 0.0
    h, w = rgb.shape[:2]
    q = np.asarray(landmarks, dtype=float)[:, :2] * [w, h]
    if not np.isfinite(q).all():
        return 0.0
    horizontal = q[291] - q[61]
    width = float(np.linalg.norm(horizontal))
    if width < 24:
        return 0.0
    horizontal /= width
    vertical = np.array([-horizontal[1], horizontal[0]])
    if np.dot(q[152] - q[13], vertical) < 0:
        vertical *= -1
    gap = float(np.dot(q[14] - q[13], vertical)) / width
    if gap < .025 and jaw_open < .045:
        return 0.0
    # One mouth-width is 100 pixels; origin is the upper inner lip.
    basis = np.stack([horizontal, vertical]) * (100 / width)
    offset = np.array([50., 8.]) - basis @ q[13]
    crop = cv2.warpAffine(rgb, np.column_stack([basis, offset]), (100, 80), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    total = np.maximum(crop.sum(axis=2), 1)
    redness = crop[:, :, 0] / total
    skin = np.concatenate([redness[40:65, 8:22].ravel(), redness[40:65, 78:92].ravel()])
    skin_red = float(np.median(skin))
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    saturation = (crop.max(axis=2) - crop.min(axis=2)) / np.maximum(crop.max(axis=2), 1)
    pink = ((r > 48) & (r > g * 1.12) & (r > b * 1.015) & (b > g * .78)
            & (saturation > .12) & (redness > max(.37, skin_red + .015)))
    yy, xx = np.indices(pink.shape)
    lower_lip = float((basis @ q[17] + offset)[1])
    pink &= (np.abs(xx - 50) < 30) & (yy > 8 + max(2, gap * 20)) & (yy < lower_lip + 35)
    mask = cv2.morphologyEx(pink.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    score = 0.0
    for component, (x, y, bw, bh, area) in enumerate(stats[1:], 1):
        if bw < 10 or bh < 8 or area < 60 or abs(x + bw / 2 - 50) > 19:
            continue
        region = labels == component
        # Evaluate the protruding part separately from the connected lip band.
        # A smile often connects both lips into a wide pink arc. Its bounding
        # box is NOT evidence of a tongue, even if one stray pixel lies below.
        below = region & (yy > lower_lip + 3) & (np.abs(xx - 50) < 26)
        by, bx = np.nonzero(below)
        if len(bx) >= 45:
            low, high = np.percentile(by, [5, 95])
            span = float(np.percentile(bx, 95) - np.percentile(bx, 5))
            extension = (high - lower_lip) / 100
            # The extension must be a narrow central lobe with substantial
            # depth; flat red lower lips and broad skin patches are rejected.
            if 10 <= span <= 47 and high-low >= 4 and (high-low)/span >= .15 and abs(float(np.median(bx))-50) < 15 and y < lower_lip+3:
                density = min(1., len(bx) / max(span * (high-low) * .9, 1))
                extent = np.clip((extension-.035)/.12, 0, 1)
                score = max(score, float(extent*density))
        # A tongue pointing toward the camera can be inside the lip outline:
        # require a central, vertically substantial patch inside the INNER lips,
        # separated from their boundaries. White teeth cannot pass the pink mask.
        inner_bottom = float((basis @ q[14] + offset)[1])
        cavity = region & (yy > 12) & (yy < inner_bottom-4) & (np.abs(xx-50) < 24)
        iy, ix = np.nonzero(cavity)
        if gap > .13 and len(ix) >= 100:
            height = float(np.percentile(iy,95)-np.percentile(iy,5))
            span = float(np.percentile(ix,95)-np.percentile(ix,5))
            if height >= 8 and 12 <= span <= 43 and height/max(span,1) > .30:
                central = np.count_nonzero(region & (np.abs(xx-50)<20) & (yy>12) & (yy<inner_bottom-3))
                lateral = np.count_nonzero(region & (np.abs(xx-50)>24) & (yy>12) & (yy<inner_bottom-3))
                if central > max(90, lateral*2.5):
                    score = max(score, float(np.clip(height/26,0,.85)))
    # Rolled/projected lips can also form a central pink lobe. Colour evidence
    # alone must not turn that deliberate closed-mouth gesture into a tongue.
    shapes=blendshapes or {}
    pout=max(shapes.get('mouthPucker',0),shapes.get('mouthShrugLower',0)*.8)
    if jaw_open<.28 and pout>.18:score*=max(0.,1-(pout-.18)*2.4)**2
    return score if math.isfinite(score) else 0.0
