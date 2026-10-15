"""Eye position only: no expression classification or stored camera frames."""
import numpy as np


def eye_position(observation):
    if observation is None or len(observation.landmarks)<264:return None
    landmarks=np.asarray(observation.landmarks,dtype=float)
    eyes=landmarks[[33,133,362,263],:2]
    if not np.isfinite(eyes).all():return None
    center=eyes.mean(axis=0)
    return {'x':float(np.clip(center[0],0,1)),'y':float(np.clip(center[1],0,1))}
