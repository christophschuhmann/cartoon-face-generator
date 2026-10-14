"""Raw video inspection artifacts; metrics do not claim emotion recognition."""
from pathlib import Path
import argparse,json,subprocess
import cv2,numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parent


def analyze(directory):
    directory=Path(directory);settings=json.loads((directory/'settings.json').read_text())
    video=directory/'video.mp4';capture=cv2.VideoCapture(str(video));frames=[]
    while True:
        ok,frame=capture.read()
        if not ok:break
        frames.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    fps=capture.get(cv2.CAP_PROP_FPS);capture.release()
    if not frames:raise ValueError('Video has no decoded frames')
    h,w=frames[0].shape[:2];indexes=np.unique(np.rint(np.linspace(0,len(frames)-1,9)).astype(int))
    board=Image.new('RGB',(512*3,284*4),'#eeeeee');pen=ImageDraw.Draw(board)
    source=ROOT/'inputs'/settings['pair']
    for col,label in enumerate(['start','middle','end']):
        image=Image.open(source/f'{label}.png').convert('RGB');image.thumbnail((512,256))
        board.paste(image,(col*512,24));pen.text((col*512+8,5),'SVG reference: '+label,fill='black')
    for i,index in enumerate(indexes):
        image=Image.fromarray(frames[index]);image.thumbnail((512,256))
        x,y=(i%3)*512,(i//3+1)*284
        board.paste(image,(x,y+24));pen.text((x+8,y+5),f'LTX frame {index}, {index/fps:.2f}s',fill='black')
        Image.fromarray(frames[index]).save(directory/f'frame_{index:04}.png')
    board.save(directory/'contact_sheet.png')
    border=np.zeros((h,w),dtype=bool);border[:round(h*.06)]=True;border[-round(h*.06):]=True
    border[:,:round(w*.06)]=True;border[:,-round(w*.06):]=True
    background=[];white=[];chroma=[];centroids=[];diffs=[]
    for i,frame in enumerate(frames):
        pixels=frame[border];background.append(float(pixels.mean()));white.append(float(np.all(pixels>=245,axis=1).mean()))
        chroma.append(float((frame.max(axis=2).astype(float)-frame.min(axis=2)).mean()))
        yy,xx=np.nonzero(cv2.cvtColor(frame,cv2.COLOR_RGB2GRAY)<128)
        centroids.append([float(xx.mean()/w),float(yy.mean()/h)] if len(xx) else [None,None])
        if i:diffs.append(float(np.abs(frame.astype(float)-frames[i-1]).mean()))
    endpoint={}
    for label,index in [('start',0),('end',len(frames)-1)]:
        original=Image.open(source/f'{label}.png').convert('RGB').resize((w,h))
        a=cv2.cvtColor(np.asarray(original),cv2.COLOR_RGB2GRAY)<128;b=cv2.cvtColor(frames[index],cv2.COLOR_RGB2GRAY)<128
        union=(a|b).sum();endpoint[label+'_foreground_iou']=float((a&b).sum()/union) if union else 1.
    metadata={'decoded_frames':len(frames),'fps':fps,'size':[w,h],'duration_seconds':len(frames)/fps,
        'border_mean_rgb':float(np.mean(background)),'border_fraction_all_channels_ge245':float(np.mean(white)),
        'mean_channel_range':float(np.mean(chroma)),'mean_adjacent_frame_difference':float(np.mean(diffs)),
        'foreground_centroid_normalized':centroids,'endpoint_metrics':endpoint,
        'scope':'Border brightness, alignment and pixel agreement only; not camera-motion proof or emotion recognition.'}
    anchors=[]
    for anchor in settings['anchors']:
        path=Path(anchor['path']);path=path if path.is_absolute() else ROOT/path
        original=Image.open(path).convert('RGB').resize((w,h))
        a=cv2.cvtColor(np.asarray(original),cv2.COLOR_RGB2GRAY)<128
        b=cv2.cvtColor(frames[anchor['frame_idx']],cv2.COLOR_RGB2GRAY)<128
        anchors.append({'frame':anchor['frame_idx'],'strength':anchor['strength'],
                        'foreground_iou':float((a&b).sum()/max(1,(a|b).sum()))})
    metadata['conditioning_anchor_metrics']=anchors
    (directory/'video_metrics.json').write_text(json.dumps(metadata,indent=2)+'\n')
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-vn','-ac','1','-ar','16000',str(directory/'speech.wav')],check=True)
    print(json.dumps({'name':directory.name,'frames':len(frames),'white_border':round(np.mean(white),3),**endpoint}),flush=True)
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path);args=parser.parse_args()
    directories=[args.directory] if args.directory else sorted((ROOT/'output').glob('*'))
    for directory in directories:
        if (directory/'timing.json').exists():analyze(directory)
