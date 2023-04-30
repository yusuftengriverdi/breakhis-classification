import math
import torch

import torch.nn as nn
import torch.nn.functional as F

from torch.autograd import Variable

from .resnet import resnet50_features
from .utilities.layers import conv1x1, conv3x3
import numpy as  np

# Source: https://github.com/c0nn3r/RetinaNet/blob/master/resnet_features.py 


class FeaturePyramid(nn.Module):
    def __init__(self, resnet):
        super(FeaturePyramid, self).__init__()

        self.resnet = resnet

        # applied in a pyramid
        self.pyramid_transformation_3 = conv1x1(512, 256)
        self.pyramid_transformation_4 = conv1x1(1024, 256)
        self.pyramid_transformation_5 = conv1x1(2048, 256)

        # both based around resnet_feature_5
        self.pyramid_transformation_6 = conv3x3(2048, 256, padding=1, stride=2)
        self.pyramid_transformation_7 = conv3x3(256, 256, padding=1, stride=2)

        # applied after upsampling
        self.upsample_transform_1 = conv3x3(256, 256, padding=1)
        self.upsample_transform_2 = conv3x3(256, 256, padding=1)

    def _upsample(self, original_feature, scaled_feature, scale_factor=2):
        # is this correct? You do lose information on the upscale...
        height, width = scaled_feature.size()[2:]
        return F.interpolate(original_feature, scale_factor=scale_factor)[:, :, :height, :width]

    def forward(self, x):

        # don't need resnet_feature_2 as it is too large
        _, resnet_feature_3, resnet_feature_4, resnet_feature_5 = self.resnet(x)

        pyramid_feature_6 = self.pyramid_transformation_6(resnet_feature_5)
        pyramid_feature_7 = self.pyramid_transformation_7(F.relu(pyramid_feature_6))

        pyramid_feature_5 = self.pyramid_transformation_5(resnet_feature_5)
        pyramid_feature_4 = self.pyramid_transformation_4(resnet_feature_4)
        upsampled_feature_5 = self._upsample(pyramid_feature_5, pyramid_feature_4)

        pyramid_feature_4 = self.upsample_transform_1(
            torch.add(upsampled_feature_5, pyramid_feature_4)
        )

        pyramid_feature_3 = self.pyramid_transformation_3(resnet_feature_3)
        upsampled_feature_4 = self._upsample(pyramid_feature_4, pyramid_feature_3)

        pyramid_feature_3 = self.upsample_transform_2(
            torch.add(upsampled_feature_4, pyramid_feature_3)
        )

        return (pyramid_feature_3,
                pyramid_feature_4,
                pyramid_feature_5,
                pyramid_feature_6,
                pyramid_feature_7)


class SubNet(nn.Module):

    def __init__(self, mode, num_classes=80, depth=4,
                 base_activation=F.relu,
                 output_activation=F.sigmoid):
        super(SubNet, self).__init__()
        self.num_classes = num_classes
        self.depth = depth
        self.base_activation = base_activation
        self.output_activation = output_activation
        self.sum_ = 0
        self.subnet_base = nn.ModuleList([conv3x3(256, 256, padding=1)
                                          for _ in range(depth)])

        #if mode == 'boxes':
        #    self.subnet_output = conv3x3(256, 4 * self.anchors, padding=1)
        if mode == 'classes':
            self.subnet_output = nn.Sequential(
                                                nn.Dropout(p=0.5),
                                                conv3x3(256, self.num_classes, padding=1),
                                                nn.ReLU(inplace=True),
                                                nn.AvgPool3d(1)
                                            )
                                                        

    def forward(self, x):
        for layer in self.subnet_base:
            x = self.base_activation(layer(x))

        x = self.subnet_output(x)
        
        x = x.permute(0, 2, 3, 1).contiguous().view(x.size(0),
                                                    x.size(2) * x.size(3), -1)

        return x


class RetinaNet(nn.Module):

    def __init__(self, num_classes, backbone=resnet50_features, use_pretrained=False):
        super(RetinaNet, self).__init__()
        self.num_classes = num_classes

        _resnet = backbone(pretrained=use_pretrained)
        self.feature_pyramid = FeaturePyramid(_resnet)

        # self.subnet_boxes = SubNet(mode='boxes', num_classes=self.num_classes)
        self.subnet_classes = SubNet(mode='classes', num_classes=self.num_classes)

    def forward(self, x):

        # boxes = []
        classes = []

        features = self.feature_pyramid(x)

        # how faster to do one loop
        # boxes = [self.subnet_boxes(feature) for feature in features]
        classes = [self.subnet_classes(feature) for feature in features]
        classes = torch.cat(classes, 1)
        classes = torch.mean(classes, dim=1)
        return classes


if __name__ == '__main__':
    import time
    import torchvision.datasets as dset

    net = RetinaNet(num_classes=10)
    # For first time downloading.
    # cifar10 = dset.CIFAR10("data/cifar10/", download=True)
    cifar10 = dset.CIFAR10("data/cifar10/", download=False)
    print(cifar10.data.shape)

    x  = torch.tensor(cifar10.data[:100]) / 255
    x = x.permute(0, 3, 1, 2)
    
    predictions = net(Variable(x))

    print(predictions.size(), predictions[0])

