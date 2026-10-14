"""Real detector predictions (orange) and ground truth (blue); no drawn guesses."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def visualize_predictions(data,predictions,visibility,out,count=12):
    classes=[0,5,15,27,31,40,42,47,60,70,80,99];selected=[]
    for cls in classes:
        options=np.flatnonzero((data['categories']==cls)&(data['conditions']=='augmented'))
        if len(options):selected.append(int(options[0]))
    if len(predictions)<=count or not selected:selected=list(range(min(count,len(predictions))))
    h,w=data['images'].shape[1:3];board=Image.new('RGB',(3*w,((len(selected)+2)//3)*(h+27)),'#e5e7eb');draw=ImageDraw.Draw(board)
    for n,i in enumerate(selected):
        im=Image.fromarray(data['images'][i]);marks=ImageDraw.Draw(im)
        for truth,pred,v in zip(data['xy'][i],predictions[i],visibility[i]):
            if not v:continue
            tx,ty=truth*[w,h];px,py=pred*[w,h]
            marks.line((tx,ty,px,py),fill='#c7a070',width=1)
            marks.ellipse((tx-2,ty-2,tx+2,ty+2),fill='#216bdf');marks.ellipse((px-2,py-2,px+2,py+2),outline='#dc6b13',width=1)
        x=n%3*w;y=n//3*(h+27);board.paste(im,(x,y+27));draw.text((x+5,y+6),str(data['keys'][i]),fill='black')
    Path(out).parent.mkdir(parents=True,exist_ok=True);board.save(out)
