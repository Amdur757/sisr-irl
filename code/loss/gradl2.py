import torch
import torch.nn as nn 

class GradL2(nn.Module): 
    def __init__(self, n_channel, cuda): 
        super(GradL2, self).__init__()
        self.hkernel = torch.zeros(size=(n_channel, n_channel, 3, 3),dtype=torch.float32)
        l = range(n_channel)
        self.hkernel[l,l] = torch.tensor([[1,2,1],[0,0,0],[-1,-2,-1]],dtype=torch.float32)
        
        self.vkernel = torch.zeros(size=(n_channel, n_channel, 3, 3), dtype=torch.float32)
        l = range(n_channel)
        self.vkernel[l,l] = torch.tensor([[1,0,-1],[2,0,-2],[1,0,-1]],dtype=torch.float32)

        if cuda: 
            self.vkernel = self.vkernel.cuda()
            self.hkernel = self.hkernel.cuda()
    
    def forward(self, input, target):
        v_edges_input = nn.functional.conv2d(input, self.vkernel)
        h_edges_input = nn.functional.conv2d(input, self.hkernel)
        
        v_edges_target = nn.functional.conv2d(target, self.vkernel)
        h_edges_target = nn.functional.conv2d(target, self.hkernel)
        
        edges_mag_input = torch.add(torch.pow(v_edges_input,2),
                                    torch.pow(h_edges_input,2))        
        edges_mag_target = torch.add(torch.pow(v_edges_target,2),
                                    torch.pow(h_edges_target,2))
        
        out = torch.mean(torch.pow(edges_mag_target - edges_mag_input, 2))        
        return out 
    