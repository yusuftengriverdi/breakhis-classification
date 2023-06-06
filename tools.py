from typing import Any
from torch.utils.data import Dataset
import numpy as np

import cv2
import glob
from tqdm import tqdm 
import re
import pandas as pd 

def alter_name(fname):
    fname = fname.split('\\')[-1]
    return fname.split('.')[0]
    
def read_images(path_arr, label, imsize=None):
    # Initialize variables
    min_width = float('inf')
    min_height = float('inf')
    resized_images = []

    # Iterate through all image files in directory
    for filename in tqdm(path_arr):
        if filename.endswith('.png'): # or any other image format
            # Read image
            img = cv2.imread(filename)
            
            # Get image width and height
            height, width, channels = img.shape
            
            # Update minimum width and height
            if width < min_width:
                min_width = width
            if height < min_height:
                min_height = height
            
            # Resize image to minimum width and height
            # resized_img = cv2.resize(img, (min_width, min_height))
            # Let's meta game here:
            
            if imsize:
                resized_img = cv2.resize(img, imsize)   
            else:
                resized_img = cv2.resize(img, (456, 700))   


            fname = alter_name(filename)
                                           
            # Add resized image to list or array
            resized_images.append((resized_img, label, fname))
    
    return resized_images

def alter_fnames_for_csv(path, save=True):
    df = pd.read_csv(path)
    df['image'] = df['image'].apply(lambda x: alter_name(x))
    if save:
        df.to_csv(path, index=False)
    return df

def binary_paths(root, mf):
    benign = root + f'benign/*/*/*/{mf}/*.png'
    malign = root + f'malignant/*/*/*/{mf}/*.png'
    return glob.glob(benign), glob.glob(malign)


def make_weights_for_balanced_classes(pairs, nclasses):  
    # Source: https://discuss.pytorch.org/t/balanced-sampling-between-classes-with-torchvision-dataloader/2703/3                       
    count = [0] * nclasses 
    for item in pairs:                                                         
        count[item[1]] += 1    
    weight_per_class = [0.] * nclasses                                      
    N = float(sum(count))                                                   
    for i in range(nclasses):                                                   
        weight_per_class[i] = N/float(count[i])                                 
    weight = [0] * len(pairs)                                              
    for idx, val in enumerate(pairs):                                          
        weight[idx] = weight_per_class[val[1]]                                  
    return weight  

class BreaKHis(Dataset):
    """TODO [reference_here]``_ Dataset.
    Args:
        root: Base directory for the images.
        labelFile: File directory to target column.
        transform: Transforms to apply on images when calling.
        shuffle: If true, the images will be shuffled.
    """
    def __init__(self, root='D:\\BreaKHis_v1\\', mf='40X', mode='binary', transform=None, target_transform = None, shuffle=True, imageLikefeatures=None):
        super(BreaKHis, self).__init__()

        self.transform = transform
        self.target_transform = target_transform
        self.shuffle = shuffle

        if mode != 'binary':
            self.nclasses = 4
            print("NOT IMPLEMENTED! Changing mode to binary...")
            mode = 'binary'
        
        if mode == 'binary':
            self.nclasses = 2
            paths = binary_paths(root, mf)
            
            benign_stack = read_images(paths[0], 0)
            malign_stack = read_images(paths[1], 1)

            pairs = np.concatenate([benign_stack, malign_stack])
            
        if shuffle:
            np.random.shuffle(pairs)

        self.images = pairs[:, 0]
        self.targets = pairs[:, 1]
        self.weight = make_weights_for_balanced_classes(pairs, self.nclasses)

        self.mean = np.mean(pairs[:, 0], axis=0)

        if imageLikefeatures:
            for imageLikefeature in imageLikefeatures:
                # TODO: read features and stack a channel.
                pass
            
    def __len__(self):
        return len(self.images)
    
    def __getitem__(self, index):
        """
        Args:
            index (int): Index
        Returns:
            tuple: Tuple (image, target).
        """

        img = self.images[index]
        target = self.targets[index]

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target
    
    
if __name__ == '__main__':
    # path = "C:\\Users\\yusuf\\Machine and Deep Learning\\breast_histopathology_clf\\features\\all\\binary\\40X\\pftas.csv"

    # alter_fnames_for_csv(path)
    

    import time
    from torchvision import transforms
    import torch
    from torch.utils.data import WeightedRandomSampler, random_split

    print("Hello User! Dataset is loading....")
    startTime = time.time()
    myDataset = BreaKHis(
                  transform=transforms.Compose([
                            transforms.ToTensor(),
                        ]))
    print("Elapsed time in min: ", (time.time() - startTime)/60)

    print("Size of dataset and samples --> ", len(myDataset), myDataset[0][0].shape)
    print("Let's try to use dataloaders...")


    generator = torch.Generator().manual_seed(42)
    
    training_data, val_data, test_data = random_split(myDataset, [0.65, 0.25, 0.1], generator=generator)
    print("Dataset is split for training, validation and test phases --> \n",
          "training:", len(training_data),
          "validation:", len(val_data),
          "test:", (len(test_data)))
    
    BATCH_SIZE = 16
    # For unbalanced dataset we create a weighted sampler                                                                                     
    weights = torch.DoubleTensor(training_data.dataset.weight)
    print(weights)                                       
    training_sampler = WeightedRandomSampler(weights, len(weights))                     
    
    train_loader = torch.utils.data.DataLoader(training_data, batch_size=BATCH_SIZE,                              
                                                             sampler = training_sampler, pin_memory=True)   
    
    weights = torch.DoubleTensor(val_data.dataset.weight)  
    print(weights)                                                                            
    val_sampler = WeightedRandomSampler(weights, len(weights))                     
    
    val_loader = torch.utils.data.DataLoader(val_data, batch_size=BATCH_SIZE,                              
                                                             sampler = val_sampler, pin_memory=True)   
    
    weights = torch.DoubleTensor(test_data.dataset.weight)                                       
    print(weights)                                       
    test_sampler = WeightedRandomSampler(weights, len(weights))    

    test_loader = torch.utils.data.DataLoader(test_data, batch_size=BATCH_SIZE,                              
                                                             sampler = test_sampler, pin_memory=True)   
      
    print("Loaders --> ", len(train_loader), len(val_loader), len(test_loader))