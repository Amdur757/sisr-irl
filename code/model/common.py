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
    def __init__(self, conv, n_feat_in, n_feat_out, kernel_size, 
        bias=True, act=nn.ReLU(True), res_scale=1.): 

        super(DenseLayer, self).__init__()
        modules_body = []
        
        modules_body.append(conv(n_feat_in, n_feat_in, kernel_size, bias=bias))
        modules_body.append(act)
        modules_body.append(conv(n_feat_in, n_feat_out, kernel_size, bias=bias))

        self.body = nn.Sequential(*modules_body)
        self.res_scale = res_scale

    def forward(self, x): 
        out = self.body(x).mul(self.res_scale)
        out = torch.cat((out, x), dim=1)

        return out 

class DenseBlock(nn.Module): 
    def __init__(self, n_layers, growth_rate, conv, kernel_size, bias=True,
         act=nn.ReLU(True), res_scale=1., denseption=True): 
        
        super(DenseBlock, self).__init__()

        self.n_layers = n_layers
        self.growth_rate = growth_rate
        self.res_scale = res_scale
        self.denseption = denseption

        feat = growth_rate
        modules_body = []

        #dense connections
        for _ in xrange(n_layers): 
            modules_body.append(DenseLayer(conv, feat, growth_rate, kernel_size,
             bias, act, res_scale))

            feat += growth_rate

        #transition layer
        modules_body.append(conv(feat, growth_rate, kernel_size, bias=True))

        self.body = nn.Sequential(*modules_body)
        return 
    
    def forward(self, x): 
        if self.denseption==True: 
            out = self.body(x[:, :self.growth_rate]).mul(self.res_scale)
            out = torch.cat((out, x),dim=1)
        else: 
            out = self.body(x).mul(self.res_scale)
        
        return out 
    
class Upsampler(nn.Sequential):
    def __init__(self, conv, scale, n_feat, bn=False, act=False, bias=True):

        m = []
        if (scale & (scale - 1)) == 0:    # Is scale = 2^n?
            for _ in range(int(math.log(scale, 2))):
                m.append(conv(n_feat, 4 * n_feat, 3, bias))
                m.append(nn.PixelShuffle(2))
                if bn: m.append(nn.BatchNorm2d(n_feat))
                if act: m.append(act())
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