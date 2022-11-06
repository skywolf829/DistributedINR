from random import gauss
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from Other.utility_functions import make_coord_grid    

class LReLULayer(nn.Module):
    def __init__(self, in_features, out_features, bias=True):
        super().__init__()
        
        self.in_features = in_features
        self.linear = nn.Linear(in_features, out_features, 
            bias=bias)
        
        self.init_weights()
    
    def init_weights(self):
        with torch.no_grad():
            nn.init.kaiming_uniform_(self.linear.weight)

    def forward(self, input):
        return F.leaky_relu(self.linear(input), 0.2)

class SineLayer(nn.Module):
    def __init__(self, in_features, out_features, bias=True,
                 is_first=False, omega_0=30):
        super().__init__()
        self.omega_0 = omega_0
        self.is_first = is_first
        
        self.in_features = in_features
        self.linear = nn.Linear(in_features, out_features, 
            bias=bias)
        
        self.init_weights()
    
    def init_weights(self):
        with torch.no_grad():
            if self.is_first:
                self.linear.weight.uniform_(-1 / self.in_features, 
                                             1 / self.in_features)      
            else:
                self.linear.weight.uniform_(-np.sqrt(6 / self.in_features) / self.omega_0, 
                                             np.sqrt(6 / self.in_features) / self.omega_0)
        
    def forward(self, input):
        return torch.sin(self.omega_0 * self.linear(input))

class SnakeAltLayer(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)        
        self.init_weights()
    
    def init_weights(self):
        with torch.no_grad():
            nn.init.xavier_normal_(self.linear.weight)
        
    def forward(self, input):
        x = self.linear(input)
        return 0.5*x + torch.sin(x)**2

class PositionalEncoding(nn.Module):
    def __init__(self, opt):
        super(PositionalEncoding, self).__init__()        
        self.opt = opt
        self.L = opt['num_positional_encoding_terms']
        self.L_terms = torch.arange(0, opt['num_positional_encoding_terms'], 
            device=opt['device'], dtype=torch.float32).repeat_interleave(2*opt['n_dims'])
        self.L_terms = torch.pow(2, self.L_terms) * torch.pi

    def forward(self, locations):
        repeats = len(list(locations.shape)) * [1]
        repeats[-1] = self.L*2
        locations = locations.repeat(repeats)
        
        locations = locations * self.L_terms# + self.phase_shift
        if(self.opt['n_dims'] == 2):
            locations[..., 0::4] = torch.sin(locations[..., 0::4])
            locations[..., 1::4] = torch.sin(locations[..., 1::4])
            locations[..., 2::4] = torch.cos(locations[..., 2::4])
            locations[..., 3::4] = torch.cos(locations[..., 3::4])
        else:
            locations[..., 0::6] = torch.sin(locations[..., 0::6])
            locations[..., 1::6] = torch.sin(locations[..., 1::6])
            locations[..., 2::6] = torch.sin(locations[..., 2::6])
            locations[..., 3::6] = torch.cos(locations[..., 3::6])
            locations[..., 4::6] = torch.cos(locations[..., 4::6])
            locations[..., 5::6] = torch.cos(locations[..., 5::6])
        return locations
       
class fVSRN(nn.Module):
    def __init__(self, opt):
        super().__init__()
        
        self.opt = opt
        self.recently_added_layer = False
        self.pe = PositionalEncoding(opt)
        
        feat_shape = [1, opt['n_features']]
        grid_shape = opt['feature_grid_shape'].split(",")
        for i in range(len(grid_shape)):
            feat_shape.append(int(grid_shape[i]))
        self.feature_grid = torch.randn(grid_shape, device=self.opt['device'], dtype=torch.float32)
        
        self.decoder = nn.ModuleList()
        first_layer_input_size = opt['num_positional_encoding_terms']*opt['n_dims']*2 + opt['n_features']
        layer = SnakeAltLayer(first_layer_input_size, 
                            opt['nodes_per_layer'], 
                            is_first=True)
        self.decoder.append(layer)
        
        for i in range(opt['n_layers']):
            if i == opt['n_layers'] - 1:
                layer = nn.Linear(opt['nodes_per_layer'], opt['n_outputs'])
                nn.init.xavier_normal_(layer.weight)
                self.decoder.append(layer)
            else:
                layer = SnakeAltLayer(opt['nodes_per_layer'], opt['nodes_per_layer'])
                self.decoder.append(layer)
            
    def add_layer(self):
        self.recently_added_layer = True
        self.previous_last_layer = self.decoder[-1]
        self.decoder.pop(-1)
        self.decoder.append(SnakeAltLayer(
            self.opt['nodes_per_layer'], 
            self.opt['nodes_per_layer'])
        )
        new_last_layer = nn.Linear(self.opt['nodes_per_layer'], 
                                   self.opt['n_outputs'])
        nn.init.normal_(new_last_layer.weight, 0, 0.001)
        self.decoder.append(new_last_layer)
        
    def forward(self, x):     
        
        pe = self.pe(x)
        feats = F.grid_sample(self.feature_grid,
                x.unsqueeze(0).unsqueeze(0).unsqueeze(0),
                mode='bilinear', align_corners=True)    
        y = torch.cat([pe, feats], dim=1)
        
        i = 0
        while i < len(self.decoder):
            if(self.recently_added_layer and i == len(self.decoder - 2)):
                
                y1 = self.previous_last_layer(y.clone())
                y2 = self.decoder[i](y.clone())
                y2 = self.decoder[i+1](y2)
                
                a = self.opt['iters_since_new_layer'] / self.opt['iters_to_train_new_layer']
                b = 1 - a
                y = b*y1 + a*y2
                i = i + 2
            else:
                y = self.decoder[i](y)
                i = i + 1
            
        return y

        