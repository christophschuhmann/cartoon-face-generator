"""Capture the existing full codec reset; no reset semantics are rewritten."""
import torch

def reset(owner):
    graph=getattr(owner,'reset_graph',None)
    if graph is None:
        def eager():
            for state in owner.states:state.reset(torch.ones_like(state.exec_mask))
        side=torch.cuda.Stream(device=owner.device)
        side.wait_stream(torch.cuda.current_stream(owner.device))
        with torch.cuda.stream(side):eager();eager()
        torch.cuda.current_stream(owner.device).wait_stream(side)
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):eager()
        owner.reset_graph=graph
    graph.replay()
