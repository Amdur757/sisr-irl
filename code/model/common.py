import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from torch.autograd import Variable

def default_conv(in_channels, out_channels, kernel_size, bias=True):
    return nn.Conv2d(
        in_channels, out_channels, kernel_size,
        padding=(kernel_size//2), bias=bias)

class MeanShift(nn.Conv2d):
    def __init__(self, rgb_range, rgb_mean, rgb_std, sign=-1):
        super(MeanShift, self).__init__(3, 3, kernel_size=1)
        std = torch.Tensor(rgb_std)
        self.weight.data = torch.eye(3).view(3, 3, 1, 1)
        self.weight.data.div_(std.view(3, 1, 1, 1))
        self.bias.data = sign * rgb_range * torch.Tensor(rgb_mean)
        self.bias.data.div_(std)
        self.requires_grad = False

class BasicBlock(nn.Sequential):
    def __init__(
        self, in_channels, out_channels, kernel_size, stride=1, bias=False,
        bn=True, act=nn.ReLU(True)):

        m = [nn.Conv2d(
            in_channels, out_channels, kernel_size,
            padding=(kernel_size//2), stride=stride, bias=bias)
        ]
        if bn: m.append(nn.BatchNorm2d(out_channels))
        if act is not None: m.append(act)
        super(BasicBlock, self).__init__(*m)

class ResBlock(nn.Module):
    def __init__(
        self, conv, n_feat, kernel_size,
        bias=True, bn=False, act=nn.ReLU(True), res_scale=1):

        super(ResBlock, self).__init__()
        m = []
        for i in range(2):
            m.append(conv(n_feat, n_feat, kernel_size, bias=bias))
            if bn: m.append(nn.BatchNorm2d(n_feat))
            if i == 0: m.append(act)

        self.body = nn.Sequential(*m)
        self.res_scale = res_scale

    def forward(self, x):
        res = self.body(x).mul(self.res_scale)
        res += x

        return res

class DenseLayer(nn.Module):
    def __init__(self, conv, n_feat_in, n_feat_out, kernel_size,bias=False,
                to_concat=True): 

        super(DenseLayer, self).__init__()
        modules_body = []
        self.to_concat = to_concat

        modules_body.append(conv(n_feat_in, n_feat_out, kernel_size,bias=bias))
        modules_body.append(nn.ReLU(True))

        self.body = nn.Sequential(*modules_body)

    def forward(self, x): 
        out = self.body(x)
        if self.to_concat: 
            out = torch.cat((out, x), dim=1)
        return out 

class RDB(nn.Module): 
    def __init__(self, n_feat_in, n_layers, growth_rate, conv, kernel_size,
                 bias=False): 
        
        super(RDB, self).__init__()

        self.n_layers = n_layers
        self.growth_rate = growth_rate
        self.n_feat_in = n_feat_in 

        feat = n_feat_in
        self.dense_layers = []

        #dense connections
        for i in xrange(n_layers): 
            layer = conv(feat,growth_rate,kernel_size,bias=bias)
            act = nn.ReLU(True)
            dense_layer = nn.Sequential(*[layer, act])
            
            self.add_module('dense_layer{}'.format(i+1),dense_layer) 
            self.dense_layers.append(dense_layer)

            feat += growth_rate
            
        self.LFF = nn.Conv2d(feat, n_feat_in, kernel_size=1, padding=0, bias=True)
        return 
    
    def forward(self, x): 
        _x = x

        feats = [x]

        for dl in self.dense_layers: 
            o = dl(x)
            x = torch.cat([x,o],dim=1)
        
        out = self.LFF(x)
        out = out + _x
        
        return out
    
class Upsampler(nn.Sequential):
    def __init__(self, conv, scale, n_feat, bn=False, act=False, bias=True,
                type='espcnn',act_kwargs={}):

        m = []
        if (scale & (scale - 1)) == 0:    # Is scale = 2^n?
            for _ in range(int(math.log(scale, 2))):

                if type=='espcnn':
                    m.append(conv(n_feat, 4 * n_feat, 3, bias))
                    m.append(nn.PixelShuffle(2))
                    if bn: m.append(nn.BatchNorm2d(n_feat))
                    if act: m.append(act(**act_kwargs))

                elif type=='deconv':
                    m.append(conv(n_feat,n_feat,2,2,padding=0,bias=bias))
                    if act: m.append(nn.ReLU(True))

        elif scale == 3:
            m.append(conv(n_feat, 9 * n_feat, 3, bias))
            m.append(nn.PixelShuffle(3))
            if bn: m.append(nn.BatchNorm2d(n_feat))
            if act: m.append(act())
        else:
            raise NotImplementedError

        super(Upsampler, self).__init__(*m)

    def forward(self, input):
        self.outputs = []

        for i, module in enumerate(self._modules.values()):
            input = module(input)
            
            if i%2:
                self.outputs.append(input)

        return input