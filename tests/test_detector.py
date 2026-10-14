import numpy as np
import pytest
torch=pytest.importorskip('torch')
from training.model import LandmarkNet,decode,landmark_loss


def test_heatmap_decode_uses_exact_annotation_coordinate_convention():
    h,w=48,80;q=torch.tensor([[[.371,.634]]]);x=(torch.arange(w)+.5)/w;y=(torch.arange(h)+.5)/h
    logits=-((x[None,None,None,:]-q[:,:,0,None,None])*w)**2/2-((y[None,None,:,None]-q[:,:,1,None,None])*h)**2/2
    assert torch.allclose(decode(logits),q,atol=1e-5)


def test_network_shapes_finite_gradient_and_absent_landmarks_do_not_add_spatial_loss():
    torch.set_num_threads(2);net=LandmarkNet();maps,presence=net(torch.rand(2,3,192,320))
    assert maps.shape==(2,101,48,80) and presence.shape==(2,101,3)
    coords=torch.rand(2,101,2);v=torch.zeros(2,101,dtype=torch.long);v[:,0]=2;ood=torch.tensor([False,True])
    loss,_=landmark_loss(maps,presence,coords,v,ood);changed=coords.clone();changed[:,1:]=.2
    other,_=landmark_loss(maps,presence,changed,v,ood)
    assert torch.allclose(loss,other) and torch.isfinite(loss)
    loss.backward();assert torch.isfinite(net.heatmaps.weight.grad).all()


def test_holdout_returns_native_boolean_tensor_for_numpy_bool_scalars(tmp_path):
    from training.train import HoldoutDataset
    path=tmp_path/'holdout.npz';np.savez(path,images=np.zeros((1,192,320,3),dtype=np.uint8),xy=np.full((1,101,2),.5,dtype=np.float32),
      visibility=np.full((1,101),2,dtype=np.uint8),ood=np.array([False]))
    sample=HoldoutDataset(path)[0];assert sample[3].dtype==torch.bool and sample[3].item() is False
