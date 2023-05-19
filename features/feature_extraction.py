from extractors.lbp import LocalBinaryPatterns
from extractors.lpq import LPQ
from extractors.glcm import GLCM
from extractors.orb import ORB
from extractors.pftas import PFTAS
from extractors.clbp import CLBP

from extractors.fos import FOS
from extractors.hog import HOG
from extractors.hos import HOS
from extractors.fft import FFT

#from extractors.lbp import LocalBinaryPatterns
#from extractors.glcm import GLCM
# from extractors.orb import ORB
from extractors.lpq import LPQ
# from extractors.pftas import PFTAS
# from extractors.cnn import CNN_extractor
import numpy as np
import pandas as pd
from tqdm import tqdm
import sys
import os
# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.getcwd(), "."))
# Add the parent directory to the Python path
sys.path.append(parent_dir)
# print(sys.path)
# Now we can import the tools module


from classifiers.stack import read_data
from torchvision import transforms

def extract_features(stacks, extractors=None, save=True, feature_dir="features/all/binary/40X/"):
    """Extract features from input images using specified feature extractors."""
    
    # Get number of samples and number of feature extractors.
    num_samples = len(stacks)
    num_features = len(extractors)

    # Initialize target matrix.
    y = np.array(stacks)[:, 1]
    # Get images.
    imgs = np.array(stacks)[:, 0]

    # Get filenames
    fnames = np.array(stacks)[:, 2]

    # Create a dictionary to save feature points related to that extractor.
    dict_ = {"image": fnames, 'label': y}

    # Build up filename.
    filename = feature_dir
    df = pd.DataFrame.from_dict(dict_)

    for extractor in extractors:
        filename += str(extractor)
        for j in tqdm(range(len(imgs))):
            feature_values = extractor.describe(imgs[j])
            for k, value in enumerate(feature_values):  
                df.loc[j, f"{str(extractor)}_{k}"] = value  
    if save:
        filename += '.csv'
        df.to_csv(filename, index=False)

    return fnames, df

if __name__ == "__main__":
    extractors = [# LocalBinaryPatterns(8, 1), 
                  # LPQ(radius=3, neighbors=8, block_size=3),
                  # GLCM(distances=[1], angles=[0, np.pi/4, np.pi/2, 3*np.pi/4], levels=256),
                  # ORB(num_keypoints=500),
                  # CLBP(radius=5, neighbors=24),
                  # PFTAS()
                  # FOS(),
                  # HOS(),
                  # FFT(),
                  ]

    mf = '40X'
    stack  = read_data(root="C:/Users/hadil/Documents/projects/Machine Learning/project/breast/", mf=mf, mode='binary',shuffle=False)
    if len(stack) == 0:
        print("Please change data dir!!")
        raise NotADirectoryError
    
    
    fnames, df = extract_features(stack, extractors=extractors, save=True, feature_dir=f'features/all/binary/{mf}/')