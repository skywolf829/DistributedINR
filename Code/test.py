from __future__ import absolute_import, division, print_function
import argparse
import os
from Other.utility_functions import PSNR, tensor_to_cdf, create_path, make_coord_grid
from Models.models import load_model, sample_grid
from Models.options import load_options
from Datasets.datasets import Dataset
import torch
import numpy as np

project_folder_path = os.path.dirname(os.path.abspath(__file__))
project_folder_path = os.path.join(project_folder_path, "..")
data_folder = os.path.join(project_folder_path, "Data")
output_folder = os.path.join(project_folder_path, "Output")
save_folder = os.path.join(project_folder_path, "SavedModels")

def model_reconstruction(model, dataset, opt):
    grid = list(dataset.data.shape[2:])
    with torch.no_grad():
        result = sample_grid(model, grid, 10000)
    result = result.to(opt['data_device'])
    result = result.permute(3, 0, 1, 2).unsqueeze(0)
    create_path(os.path.join(output_folder, "Reconstruction"))
    tensor_to_cdf(result, 
        os.path.join(output_folder, 
        "Reconstruction", opt['save_name']+".nc"))
    
    p = PSNR(dataset.data, result, in_place=True)
    print(f"PSNR: {p : 0.03f}")

def error_volume(model, dataset, opt):
    grid = list(dataset.data.shape[2:])
    with torch.no_grad():
        result = sample_grid(model, grid, 10000)
    result = result.to(opt['data_device'])
    result = result.permute(3, 0, 1, 2).unsqueeze(0)
    create_path(os.path.join(output_folder, "ErrorVolume"))
    
    result -= dataset.data
    result.abs_()
    tensor_to_cdf(result, 
        os.path.join(output_folder, "ErrorVolume",
        opt['save_name'] + "_error.nc"))

def scale_distribution(model, opt):
    import matplotlib.pyplot as plt
    x_scales = model.grid_scales[:,0].detach().cpu().numpy()
    y_scales = model.grid_scales[:,1].detach().cpu().numpy()
    z_scales = model.grid_scales[:,2].detach().cpu().numpy()
    plt.hist(x_scales, alpha=0.4, bins=20, label="X scales")
    plt.hist(y_scales, alpha=0.4, bins=20, label="Y scales")
    plt.hist(z_scales, alpha=0.4, bins=20, label="Z scales")
    plt.legend(loc='upper right')
    plt.title("Scale distributions")
    create_path(os.path.join(output_folder, "ScaleDistributions"))
    plt.savefig(os.path.join(output_folder, "ScaleDistributions", opt['save_name']+'.png'))

def feature_locations(model, opt):
    if(opt['model'] == "afVSRN"):
        feat_locations = model.feature_locations.detach().cpu().numpy()
        np.savetxt(os.path.join(output_folder, "feature_locations", opt['save_name']+".csv"),
                feat_locations, delimiter=",")
    elif(opt['model'] == "AMRSRN"):
        feat_grid_shape = opt['feature_grid_shape'].split(',')
        feat_grid_shape = [eval(i) for i in feat_grid_shape]
        with torch.no_grad():
            global_points = make_coord_grid(feat_grid_shape, opt['device'], 
                                flatten=True, align_corners=True)
            
            print(f"Ex transform matrix 1: {model.get_transformation_matrices()[0]}")
            print(f"Ex transform matrix 2: {model.get_transformation_matrices()[1]}")
            
            transformed_points = torch.cat([global_points, torch.ones(
                [global_points.shape[0], 1], 
                device=opt['device'],
                dtype=torch.float32)], 
                dim=1)
            transformed_points = transformed_points.unsqueeze(0).expand(
                opt['n_grids'], transformed_points.shape[0], transformed_points.shape[1])
            local_to_global_matrices = torch.inverse(model.get_transformation_matrices().transpose(-1, -2))
            transformed_points = torch.bmm(transformed_points, 
                                        local_to_global_matrices)
            transformed_points = transformed_points[...,0:3].detach().cpu()
            ids = torch.arange(transformed_points.shape[0])
            ids = ids.unsqueeze(1).unsqueeze(1)
            ids = ids.repeat([1, transformed_points.shape[1], 1])
            transformed_points = torch.cat((transformed_points, ids), dim=2)
            transformed_points = transformed_points.flatten(0,1).numpy()
        #transformed_points = transformed_points.astype(str)
        create_path(os.path.join(output_folder, "FeatureLocations"))

        np.savetxt(os.path.join(output_folder, "FeatureLocations", opt['save_name']+".csv"),
                transformed_points, delimiter=",", header="x,y,z,id")
        
        print(f"Largest/smallest transformed points: {transformed_points.min()} {transformed_points.max()}")
    
def perform_tests(model, data, tests, opt):
    if("reconstruction" in tests):
        model_reconstruction(model, data, opt),
    if("feature_locations" in tests):
        feature_locations(model, opt)
    if("error_volume" in tests):
        error_volume(model, data, opt)
    if("scale_distribution" in tests):
        scale_distribution(model, opt)
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Evaluate a model on some tests')

    parser.add_argument('--load_from',default=None,type=str,help="Model name to load")
    parser.add_argument('--tests_to_run',default=None,type=str,
                        help="A set of tests to run, separated by commas")
    parser.add_argument('--device',default=None,type=str,
                        help="Device to load model to")
    parser.add_argument('--data_device',default=None,type=str,
                        help="Device to load data to")
    args = vars(parser.parse_args())

    project_folder_path = os.path.dirname(os.path.abspath(__file__))
    project_folder_path = os.path.join(project_folder_path, "..")
    data_folder = os.path.join(project_folder_path, "Data")
    output_folder = os.path.join(project_folder_path, "Output")
    save_folder = os.path.join(project_folder_path, "SavedModels")
    
    tests_to_run = args['tests_to_run'].split(',')
    
    # Load the model
    opt = load_options(os.path.join(save_folder, args['load_from']))
    opt['device'] = args['device']
    opt['data_device'] = args['data_device']
    model = load_model(opt, args['device']).to(args['device'])
    model.train(False)
    model.eval()
    
    # Load the reference data
    data = Dataset(opt)
    
    # Perform tests
    perform_tests(model, data, tests_to_run, opt)
    
        
    
        



        

