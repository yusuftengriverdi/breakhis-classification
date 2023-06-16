import torch
import torch.nn as nn
import matplotlib.pyplot as plt
from tqdm import tqdm
from torchmetrics import Accuracy, Recall, AveragePrecision, AUROC, F1Score, CohenKappa, Specificity
import pandas as pd
import datetime
import numpy as np
import torch.nn.functional as F
from . import visualize
from torchvision import transforms as T
import cv2
import numpy as np
from skimage.color import rgb2hed, hed2rgb


p = 0.8
r = 0.3
# Define the data augmentation transformations for each class
majority_transforms = T.RandomApply(transforms=[
    T.RandomVerticalFlip(p=0.5), 
    T.RandomHorizontalFlip(p=0.5), 
    T.ElasticTransform(alpha=50.0, sigma=2.0), 
    T.RandomPerspective(p=0.5, distortion_scale=0.2),
    T.ColorJitter(brightness=.5, hue=.3),
    T.GaussianBlur(kernel_size=(5, 9), sigma=(0.1, 5))
    # Add other transformations for the minority class as desired
], p= p*r)


minority_transforms = T.RandomApply(transforms=[
    T.RandomVerticalFlip(p=0.5), 
    T.RandomHorizontalFlip(p=0.5), 
    T.ElasticTransform(alpha=50.0, sigma=2.0), 
    T.RandomPerspective(p=0.5, distortion_scale=0.2),
    T.ColorJitter(brightness=.5, hue=.3),
    T.GaussianBlur(kernel_size=(5, 9), sigma=(0.1, 5))
    # Add other transformations for the minority class as desired
], p= p*(1-r))

# Define the elastic transform function with adjustable probability
def apply_on_air_augmentation(X, y, n, r=0.1,
                              majority_transforms=majority_transforms,
                              minority_transforms=majority_transforms,
                              device='cpu'):
    # Assuming you have the augmented majority and minority samples
    majority_X_aug = torch.stack([majority_transforms(X[y == 1]) for _ in range(n)], dim=1)
    minority_X_aug = torch.stack([minority_transforms(X[y == 0]) for _ in range(n)], dim=1)

    majority_X_aug = majority_X_aug.view(-1, *majority_X_aug.shape[2:])
    minority_X_aug = minority_X_aug.view(-1, *minority_X_aug.shape[2:])

    # Get the desired number of samples from each class
    num_samples_majority = int(n * 32 * r)  # Number of samples from majority class
    num_samples_minority = int(n * 32 * (1 - r))  # Number of samples from minority class

    # Generate random indices for sampling
    majority_indices = torch.randperm(len(majority_X_aug))[:num_samples_majority]
    minority_indices = torch.randperm(len(minority_X_aug))[:num_samples_minority]

    selected_majority_X_aug = torch.cat([majority_X_aug[i].unsqueeze(0) for i in majority_indices], dim=0)
    selected_minority_X_aug = torch.cat([minority_X_aug[i].unsqueeze(0) for i in minority_indices], dim=0)

    # Stack the selected samples and target values
    selected_X_aug = torch.cat([selected_majority_X_aug, 
                                selected_minority_X_aug], 
                                dim=0)
    
    selected_y = torch.cat([torch.ones(len(selected_majority_X_aug)).unsqueeze(-1), 
                            torch.zeros(len(selected_minority_X_aug)).unsqueeze(-1)], 
                            dim=0).squeeze(-1)

    return selected_X_aug, selected_y

import cv2
import numpy as np

def divide_images_into_patches(images, targets_y, patch_size, device, mean_per_ch, std_per_ch,
                    method=cv2.ximgproc.SLICO):
    
    transform = T.Compose([
                    T.ToPILImage(),  # Convert numpy.ndarray to PIL Image
                    T.Resize(256),
                    T.CenterCrop(224),
                    T.ToTensor(),
                    T.Normalize(mean=mean_per_ch[:-1], std=std_per_ch[:-1])
                ])
    # Generate patches based on superpixels
    patches = []
    targets = []

    # fig, axs = plt.subplots(10, 5, figsize=(12, 6))
    # axs = axs.ravel()
    # count = 0

    for ind, image in enumerate(images):
        image = image.cpu().numpy()
        image = np.transpose(image, axes=(1, 2, 0))

        image = cv2.GaussianBlur(image, (3, 3), 0)
        # Convert image to Lab color space for better superpixel segmentation
        image_lab = cv2.cvtColor(image, cv2.COLOR_RGB2Lab)
        # Separate the stains from the IHC image
        hed = rgb2hed(image)
        null = np.zeros_like(hed[:, :, 0])
        ihc_h = hed2rgb(np.stack((hed[:, :, 0], null, null), axis=-1))
        ihc_e = hed2rgb(np.stack((null, hed[:, :, 1], null), axis=-1))
        ihc_d = hed2rgb(np.stack((null, null, hed[:, :, 2]), axis=-1))
  
        # instance and run SLIC
        slic = cv2.ximgproc.createSuperpixelSLIC(image_lab, method, 100)
        slic.iterate(50)

        # replace original image pixels with superpixels means
        labels = slic.getLabels()

        unique_labels = np.unique(labels)
        for label in unique_labels:
            mask = labels == label
            # Calculate the bounding box of the superpixel
            x, y, w, h = cv2.boundingRect(mask.astype(np.uint8))
            # Crop the corresponding region from the original image
            patch = image[y:y+h, x:x+w, :]
            patch = cv2.resize(patch, patch_size)
            # if count < 50:
            #     # print(np.nonzero(patch))
            #     axs[count].imshow(patch)
            #     axs[count].axis('off')
            #     count += 1
            # else:
            #     plt.tight_layout()
            #     plt.show()
            transformed_patch = transform(torch.Tensor(np.transpose(patch, axes=(-1, 0, 1)))).to(device)

            patches.append(transformed_patch)    
            targets.append(targets_y[ind])

    patches = torch.stack(patches)
    targets = torch.Tensor(targets)



    return patches, targets


def train(model, train_loader, optimizer, criterion, eval_metrics, device, 
          mean_per_ch, std_per_ch,
          aug=False, 
          patch=True,
          epoch=-1):

    average_loss = 0
    metric_values = {metric_name: [] for metric_name in eval_metrics.keys()}

    # model.to(device)
    if device != 'cpu':
        model = nn.DataParallel(model.to(device))

    for batch, (X, y) in enumerate(train_loader):

        optimizer.zero_grad()

        X = X.to(device)
        y = y.to(device)
        # print("Before", np.unique(y.cpu().detach().numpy(), return_counts=True))

        # Apply on-the-fly augmentation to obtain augmented data and labels
        if aug:
            X_aug, y_aug = apply_on_air_augmentation(X, y, n=1)

            X_aug = X_aug.to(device)
            y_aug = y_aug.to(device)
            # Stack original and augmented data
            stacked_X = torch.cat((X, X_aug))
            stacked_y = torch.cat((y, y_aug))

            # Shuffle the stacked data and labels
            indices = torch.randperm(stacked_X.size(0))
            X = stacked_X[indices]
            y = stacked_y[indices]

        if patch:
            patch_X, patch_y = divide_images_into_patches(X, y, (226, 226), device, mean_per_ch, std_per_ch)
            patch_X = torch.Tensor(patch_X).to(device)
            patch_y = torch.Tensor(patch_y).to(device)

            print(patch_X.size(), patch_y.size())

        X = patch_X
        y = patch_y
        # print("After", np.unique(y.cpu().detach().numpy(), return_counts=True))
        X = X.requires_grad_()
        yhat = model(X)
        if not isinstance(yhat, torch.Tensor):
            yhat = yhat[0]

        yhat = yhat.to(device)
        y = y.long()
        y_vectors = F.one_hot(y, 2)
        # print(yhat.size(), y.size(), y_vectors.size())
        loss = criterion(yhat, y)
        
        # Update model, gradient descent.
        loss.backward()
        optimizer.step()
        average_loss += loss.item()

        # Compute evaluation metrics
        with torch.no_grad():
            yhat_labs = torch.argmax(yhat, dim=1).to(device)
            for metric_name, metric in eval_metrics.items():
                try:
                    # Try as one-hot-vectors.
                    # print("I tried THIS!")
                    metric_val = metric(yhat_labs, y)
                except ValueError as e:
                    # Try as logits. 
                    # print("BUT IT DIDNT WORK SO!")
                    metric_val = metric(yhat, y_vectors)
                
                metric_values[metric_name].append(metric_val.item())

        if batch % 10 == 0:
            #  print(f"loss: {loss:>7f}, average loss: {average_loss/len(train_loader):>5f}")
            pass

    average_loss /= (batch +1)
    epoch_scores = {
        'Epoch': epoch + 1,
        'Average Loss': average_loss,
        **{metric_name: sum(metric_values[metric_name]) / len(metric_values[metric_name]) for metric_name in eval_metrics}
    }

    print(epoch_scores)
    return epoch_scores

def test(model, test_loader, criterion, eval_metrics, device, mean_per_ch, std_per_ch, epoch=-1, mode='binary', patch=True):

    average_loss = 0
    metric_values = {metric_name: [] for metric_name in eval_metrics.keys()}

    # model.to(device)
    if device != 'cpu':
        model = nn.DataParallel(model)

    for X, y in test_loader:
        X = X.to(device)
        y = y.to(device)

        with torch.no_grad():
            
            if patch:
                patch_X, patch_y = divide_images_into_patches(X, y, (226, 226), device, mean_per_ch, std_per_ch)
                patch_X = torch.Tensor(patch_X).to(device)
                patch_y = torch.Tensor(patch_y).to(device)

            X = patch_X
            y = patch_y
            X = X.requires_grad_()
            yhat = model(X)
            if not isinstance(yhat, torch.Tensor):
                yhat = yhat[0]

            y_vectors = F.one_hot(y, 2)
            # print(yhat.size(), y.size(), y_vectors.size())
            # print("Test", np.unique(y.cpu().detach().numpy(), return_counts=True))
            # print(y)

            loss = criterion(yhat, y)
            average_loss += loss.item()

            # Convert labels to one-hot vectors and vice-versa.
            y_vectors = torch.eye(2, device=device, dtype=torch.long)[y]
            yhat_labs = torch.argmax(yhat, dim=1).to(device)
            for metric_name, metric in eval_metrics.items():
                try:
                    # Try as one-hot-vectors.
                    # print("I tried THIS!")
                    metric_val = metric(yhat_labs, y)
                except ValueError as e:
                    # Try as logits. 
                    # print("BUT IT DIDNT WORK SO!")
                    metric_val = metric(yhat, y_vectors)

                metric_values[metric_name].append(metric_val.item())
        
    average_loss /= len(test_loader)
    epoch_scores = {
        'Epoch': epoch + 1,
        'Average Loss': average_loss,
        **{metric_name: sum(metric_values[metric_name]) / len(metric_values[metric_name]) for metric_name in eval_metrics}
    }

    print(epoch_scores)
    return epoch_scores

def eval(model, test_loader, train_loader, optimizer, criterion, device, mean_per_ch, std_per_ch,
            num_epochs= 1, mode='binary', model_name=None, mf='40X'):

    eval_metrics = {
    'accuracy_score': Accuracy(task=mode).to(device),
    'roc_auc_score': AUROC(task=mode).to(device),
    'average_precision_score' : AveragePrecision(task=mode).to(device),
    'f1_score' : F1Score(mode).to(device),
    'recall_Score' : Recall(mode).to(device),
    'cohen_kappa_score' : CohenKappa(mode).to(device),
    'specificity': Specificity(mode).to(device)
    }

    m_titles = {
    'accuracy_score': 'Accuracy',
    'roc_auc_score': 'ROC AUC',
    'average_precision_score' : 'Average Precision',
    'f1_score' : 'F1 Score',
    'recall_Score' : 'Recall',
    'cohen_kappa_score' : 'Cohen-Kappa Score',
    'specificity': 'Specificity'
    }

    # TODO:  Add pattern recognition rate.

    for t in tqdm(range(num_epochs), desc='Training on Breast Histopathology Dataset', unit='epoch'):
        print(f"Epoch {t+1}\n-------------------------------")
        train_scores = train(model, train_loader, optimizer, criterion, eval_metrics, device, mean_per_ch, std_per_ch, 
                             epoch = t)
        test_scores = test(model, test_loader, criterion, eval_metrics, device, mean_per_ch, std_per_ch,  epoch= t)
        if t == 0:
            train_df = pd.DataFrame(train_scores, index=[0])
            test_df = pd.DataFrame(test_scores, index=[0])
        else:
            train_df = pd.concat([train_df, pd.DataFrame(train_scores, index=[0])])
            test_df = pd.concat([test_df, pd.DataFrame(test_scores, index=[0])])
    
    # Save the DataFrame as a CSV file
    if not model_name:
        model_name = model.__class__.__name__

    # Get the current date
    current_date = datetime.date.today()

    # Convert the date to a string
    date_string = current_date.strftime("%Y-%m-%d")

    train_df.to_csv(f'models/results/{mf}/train/{model_name}_{date_string}.csv', index=False)
    test_df.to_csv(f'models/results/{mf}/test/{model_name}_{date_string}.csv', index=False)

    # Save only the model's state dictionary (i.e. weights) as it is built-in model.
    torch.save(model.state_dict(), f'models/results/{mf}/weights/{model_name}_{date_string}.pth')

    for metric, title in m_titles.items():
        visualize.visualize_metrics(train_data=train_df, test_data=test_df, 
                                path=f'models/results/40X/figs/{model_name}_{date_string}_{metric}.png',
                                metric=metric,
                                title=title)
    print(model_name, "Done!")
