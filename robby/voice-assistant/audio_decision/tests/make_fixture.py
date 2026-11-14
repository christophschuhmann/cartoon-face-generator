"""Author the public test stimulus; no microphone recordings or third-party audio."""
from pathlib import Path
import numpy as np,soundfile as sf
p=Path(__file__).parent/'fixtures';p.mkdir(exist_ok=True)
sr=48000;t=np.arange(sr*4)/sr;wave=np.zeros(len(t),np.float32)
for a,b,f,amp in [(.6,1.3,880,.25),(2.2,3.2,440,.2)]:
 mask=(t>a)&(t<b);wave[mask]=amp*np.sin(2*np.pi*f*t[mask])
sf.write(p/'beeps.wav',wave,sr)
