from random import gauss
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from Other.utility_functions import make_coord_grid    
from Models.layers import LReLULayer, SineLayer, SnakeAltLayer, PositionalEncoding

       
class AMRSRN(nn.Module):
    def __init__(self, opt):
        super().__init__()
        
        self.opt = opt
        
        feat_grid_shape = opt['feature_grid_shape'].split(',')
        feat_grid_shape = [eval(i) for i in feat_grid_shape]
        
        init_scales = torch.ones(
                [self.opt['n_grids'], 3],
                device = opt['device']
            ).uniform_(1,4)

        init_translations = torch.zeros(
                [self.opt['n_grids'], 3],
                device = opt['device']
            ).uniform_(-1, 1) * (init_scales-1)

        #init_grid_transforms = torch.zeros(
        #        [self.opt['n_grids'], 4, 4],
        #        device = opt['device']
        #    ).normal_(1, 1)
        
        #init_grid_transforms[:,-1,:] = 0
        #init_grid_transforms[:,-1,-1] = 1
        #init_grid_transforms[:] = torch.eye(4,
        #                    dtype=torch.float32,
        #                    device=opt['device'])
    
        self.grid_scales = torch.nn.Parameter(
            init_scales,
            requires_grad=True
        )
        self.grid_translations = torch.nn.Parameter(
            init_translations,
            requires_grad=True
        )
        #self.feature_grid_transform_matrices =  torch.nn.parameter.Parameter(
        #    init_grid_transforms,
        #    requires_grad=True
        #)
        
        self.feature_grids =  torch.nn.parameter.Parameter(
            torch.ones(
                [self.opt['n_grids'], self.opt['n_features'], 
                feat_grid_shape[0], feat_grid_shape[1], feat_grid_shape[2]],
                device = opt['device']
            ).normal_(0, 1),
            requires_grad=True
        )
        
        self.pe = PositionalEncoding(opt)
        
        self.decoder = nn.ModuleList()
        
        first_layer_input_size = opt['n_features']*opt['n_grids'] + opt['num_positional_encoding_terms']*opt['n_dims']*2
                 
        layer = SnakeAltLayer(first_layer_input_size, 
                            opt['nodes_per_layer'])
        self.decoder.append(layer)
        
        for i in range(opt['n_layers']):
            if i == opt['n_layers'] - 1:
                layer = nn.Linear(opt['nodes_per_layer'] + opt['n_features']*opt['n_grids'], opt['n_outputs'])
                nn.init.xavier_normal_(layer.weight)
                self.decoder.append(layer)
            else:
                layer = SnakeAltLayer(opt['nodes_per_layer'] + opt['n_features']*opt['n_grids'], opt['nodes_per_layer'])
                self.decoder.append(layer)
    
    def get_transformation_matrices(self):
        transformation_matrices = torch.zeros(
                [self.opt['n_grids'], 4, 4],
                device = self.opt['device']
            )
        transformation_matrices[:,-1,-1] = 1
        transformation_matrices[:,0,0] = self.grid_scales[:,0]
        transformation_matrices[:,1,1] = self.grid_scales[:,1]
        transformation_matrices[:,2,2] = self.grid_scales[:,2]
        transformation_matrices[:,0:3,-1] = self.grid_translations
        return transformation_matrices

    def forward(self, x):   
        
        transformed_points = torch.cat([x, torch.ones([x.shape[0], 1], 
            device=self.opt['device'],
            dtype=torch.float32)], 
            dim=1)
        transformed_points = transformed_points.unsqueeze(0).repeat(
            self.opt['n_grids'], 1, 1)
        transformation_matrices = self.get_transformation_matrices()
        
        transformed_points = torch.bmm(transformation_matrices, 
                            transformed_points.transpose(-1, -2)).transpose(-1, -2)
        transformed_points = transformed_points[...,0:3]
       
        
        transformed_points = transformed_points.unsqueeze(1).unsqueeze(1)
        feats = F.grid_sample(self.feature_grids,
                transformed_points,
                mode='bilinear', align_corners=True,
                padding_mode="zeros")[:,:,0,0,:]
        # test 1
        feats = feats.flatten(0,1).permute(1, 0)
        #feats = feats.detach()
        

        # test 2
        #feats = feats.sum(dim=0).permute(1, 0)

        # test 3
        #feats = feats.reshape(16, -1, feats.shape[1], feats.shape[2])
        #feats = feats.sum(dim=0).flatten(0,1).permute(1, 0)
        
        if(self.opt['use_global_position']):
            x = x + 1.0
            x = x / 2.0
            x = x * self.dim_global_proportions
            x = x + self.dim_start
        
        pe = self.pe(x.detach())  
        y = pe
        #y = feats.clone()
        
        i = 0
        while i < len(self.decoder):
            y = torch.cat([y, feats], dim=1)
            y = self.decoder[i](y)
            i = i + 1
            
        return y

        