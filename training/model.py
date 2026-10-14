"""Compact fully convolutional 101-heatmap detector, no pretrained identity model."""
import torch
from torch import nn
from torch.nn import functional as F


class Block(nn.Sequential):
    def __init__(self,inputs,outputs,stride=1):
        super().__init__(nn.Conv2d(inputs,outputs,3,stride,1,bias=False),nn.BatchNorm2d(outputs),nn.SiLU(),
          nn.Conv2d(outputs,outputs,3,1,1,bias=False),nn.BatchNorm2d(outputs),nn.SiLU())


class LandmarkNet(nn.Module):
    def __init__(self,landmarks=101):
        super().__init__();self.landmarks=landmarks
        self.e0=Block(3,24,2);self.e1=Block(24,48,2);self.e2=Block(48,96,2);self.e3=Block(96,160,2)
        self.d2=Block(256,96);self.d1=Block(144,64)
        self.heatmaps=nn.Conv2d(64,landmarks,1);self.presence=nn.Linear(160,landmarks*3)
    def forward(self,image):
        a=self.e0(image);b=self.e1(a);c=self.e2(b);d=self.e3(c)
        up=self.d2(torch.cat([F.interpolate(d,size=c.shape[-2:],mode='bilinear',align_corners=False),c],1))
        up=self.d1(torch.cat([F.interpolate(up,size=b.shape[-2:],mode='bilinear',align_corners=False),b],1))
        return self.heatmaps(up),self.presence(d.mean((-2,-1))).reshape(-1,self.landmarks,3)


def decode(heatmaps):
    """Spatial expectation in the same [x/W,y/H] convention as annotations."""
    n,k,h,w=heatmaps.shape;prob=heatmaps.float().flatten(2).softmax(-1).reshape(n,k,h,w)
    x=(torch.arange(w,device=heatmaps.device,dtype=torch.float32)+.5)/w
    y=(torch.arange(h,device=heatmaps.device,dtype=torch.float32)+.5)/h
    return torch.stack([(prob.sum(-2)*x).sum(-1),(prob.sum(-1)*y).sum(-1)],-1)


def landmark_loss(heatmaps,presence,coordinates,visibility,ood):
    _,_,h,w=heatmaps.shape;device=heatmaps.device
    x=(torch.arange(w,device=device,dtype=torch.float32)+.5)/w
    y=(torch.arange(h,device=device,dtype=torch.float32)+.5)/h
    dx=(x[None,None,None,:]-coordinates[:,:,0,None,None])*w
    dy=(y[None,None,:,None]-coordinates[:,:,1,None,None])*h
    target=torch.exp(-(dx**2+dy**2)/(2*1.15**2)).flatten(2)
    target=target/(target.sum(-1,keepdim=True)+1e-12)
    weights=(visibility==2).float()+.35*(visibility==1).float()
    weights*=torch.where(ood[:,None],.25,1.)
    spatial=-(target*heatmaps.float().flatten(2).log_softmax(-1)).sum(-1)
    regression=F.smooth_l1_loss(decode(heatmaps),coordinates,reduction='none').sum(-1)
    spatial_loss=(spatial*weights).sum()/weights.sum().clamp_min(1)
    regression_loss=(regression*weights).sum()/weights.sum().clamp_min(1)
    presence_loss=F.cross_entropy(presence.float().flatten(0,1),visibility.long().flatten())
    total=spatial_loss+10*regression_loss+.12*presence_loss
    return total,{'spatial':spatial_loss.detach(),'coordinate':regression_loss.detach(),'presence':presence_loss.detach()}
