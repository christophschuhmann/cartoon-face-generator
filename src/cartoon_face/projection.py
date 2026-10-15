"""Optional curved face projection. Canonical 101 keypoints stay editable in 2D.

Projects generated SVG control points onto a shallow ellipsoid, with extra nose
depth. This is a stylized 2.5D face, not a reconstructed human head. Legacy poses
without the projection flag retain their original rendering.
"""
import re
import math
import numpy as np

NUMBER = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?')


class FaceProjection:
    def __init__(self, head):
        self.yaw = float(np.clip(head.get('yaw', 0), -.85, .85))
        self.pitch = float(np.clip(head.get('pitch', 0), -.55, .55))

    def points(self, points, nose=False):
        q = np.asarray(points, dtype=float)
        x, y = q[..., 0] - 725., q[..., 1] - 375.
        # Smooth broad curvature gives near/far eyes different scale and motion.
        radius = (x / 820.) ** 2 + (y / 650.) ** 2
        z = 245. * np.sqrt(np.maximum(.16, 1. - radius))
        if nose: z = z + 110.
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        xx, zz = cy * x + sy * z, -sy * x + cy * z
        yy, zz = cp * y + sp * zz, -sp * y + cp * zz
        perspective = (1650. - z) / (1650. - zz)
        # A little cartoon compensation keeps broad turns from looking crushed.
        xx = xx * perspective * (1. + .24 * sy * sy)
        yy = yy * perspective
        return np.stack([xx + 725., yy + 375.], axis=-1)

    def path(self, path, nose=False):
        values = np.array([float(v) for v in NUMBER.findall(path)])
        if len(values) % 2: raise ValueError('Expected cubic/line SVG coordinate pairs')
        projected = iter(self.points(values.reshape(-1, 2), nose).ravel())
        return NUMBER.sub(lambda _: f'{next(projected):.5f}', path)

    def shape(self, shape):
        shape = dict(shape)
        if shape['kind'] == 'path':
            shape['d'] = self.path(shape['d'], shape['id'] == 'nose')
        else:
            center = np.asarray(shape['center'])
            target = self.points(center)
            # Local tangent projection of an ellipse, with the same parent eye
            # clip as its lid. Matrix interpolation avoids ellipse-axis flips.
            jac = np.column_stack([(self.points(center + axis) - self.points(center - axis)) / 2
                                   for axis in (np.array([1., 0.]), np.array([0., 1.]))])
            angle = math.radians(shape.get('angle', 0))
            rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
            matrix = jac @ rotation
            delta = target - matrix @ center
            shape['matrix'] = [matrix[0, 0], matrix[1, 0], matrix[0, 1], matrix[1, 1], *delta]
        return shape
