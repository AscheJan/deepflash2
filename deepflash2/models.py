# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_models.ipynb (unless otherwise specified).

__all__ = ['UNetConvBlock', 'UNetUpBlock', 'UNet2D', 'unet_ronneberger2015', 'unet_falk2019', 'unet_deepflash2',
           'unet_custom']

# Cell
import torch
from torch import nn
import torch.nn.functional as F
import urllib

# Cell
class UNetConvBlock(nn.Module):
    def __init__(self, in_size, out_size, padding, batch_norm,
                 dropout=0., neg_slope=0.1):
        super(UNetConvBlock, self).__init__()
        block = []

        if dropout>0.:
            block.append(nn.Dropout(p=dropout))
        block.append(nn.Conv2d(in_size, out_size, kernel_size=3, padding=int(padding)))
        if batch_norm:
            block.append(nn.BatchNorm2d(out_size))
        block.append(nn.LeakyReLU(negative_slope=neg_slope))


        block.append(nn.Conv2d(out_size, out_size, kernel_size=3, padding=int(padding)))
        if batch_norm:
            block.append(nn.BatchNorm2d(out_size))
        block.append(nn.LeakyReLU(negative_slope=neg_slope))

        self.block = nn.Sequential(*block)

    def forward(self, x):
        out = self.block(x)
        return out

# Cell
class UNetUpBlock(nn.Module):
    def __init__(self, in_size, out_size, up_mode, padding, batch_norm,
                 dropout=0., neg_slope=0.1):
        super(UNetUpBlock, self).__init__()
        up_block = []
        if dropout>0.:
            up_block.append(nn.Dropout(p=dropout))
        if up_mode == 'upconv':
            up_block.append(nn.ConvTranspose2d(in_size, out_size, kernel_size=2, stride=2))
        elif up_mode == 'upsample':
            up_block.append(nn.Upsample(mode='bilinear', scale_factor=2))
            up_block.append(nn.Conv2d(in_size, out_size, kernel_size=1))
        if batch_norm:
            up_block.append(nn.BatchNorm2d(out_size))
        up_block.append(nn.LeakyReLU(negative_slope=neg_slope))

        self.up = nn.Sequential(*up_block)
        self.conv_block = UNetConvBlock(in_size, out_size, padding, batch_norm)

    def center_crop(self, layer, target_size):
        _, _, layer_height, layer_width = layer.size()
        diff_y = (layer_height - target_size[0]) // 2
        diff_x = (layer_width - target_size[1]) // 2
        return layer[
            :, :, diff_y : (diff_y + target_size[0]), diff_x : (diff_x + target_size[1])
        ]

    def forward(self, x, bridge):
        up = self.up(x)
        crop1 = self.center_crop(bridge, up.shape[2:])
        out = torch.cat([up, crop1], 1)
        out = self.conv_block(out)

        return out

# Cell
class UNet2D(nn.Module):
    "Pytorch U-Net Implementation"
    def __init__(
        self,
        in_channels=1,
        n_classes=2,
        depth=5,
        wf=6,
        padding=False,
        batch_norm=False,
        dropout = 0.,
        neg_slope=0.,
        up_mode='upconv',
    ):

        super().__init__()
        assert up_mode in ('upconv', 'upsample')
        self.padding = padding
        self.depth = depth
        prev_channels = in_channels
        self.down_path = nn.ModuleList()
        for i in range(depth):
            if batch_norm:
                bn = True if i>0 else False
            else:
                bn = False
            if dropout>0.:
                do = dropout if i>2 else 0.
            else:
                do = 0.
            self.down_path.append(
                UNetConvBlock(prev_channels, 2 ** (wf + i), padding,
                              batch_norm=bn, dropout=do,neg_slope=neg_slope)
            )
            prev_channels = 2 ** (wf + i)

        self.up_path = nn.ModuleList()
        for i in reversed(range(depth - 1)):
            if batch_norm:
                bn = True if i>0 else False
            else:
                bn = False
            if dropout>0.:
                do = dropout if i>2 else 0.
            else:
                do = 0.
            self.up_path.append(
                UNetUpBlock(prev_channels, 2 ** (wf + i), up_mode, padding,
                            batch_norm=bn, dropout=do, neg_slope=neg_slope)
            )
            prev_channels = 2 ** (wf + i)

        self.last = nn.Conv2d(prev_channels, n_classes, kernel_size=1)

    def _initialize_weights(self):
        """Initialize layer weights"""
        for m in self.modules():
            if isinstance(m, nn.Conv2d) or isinstance(m, nn.ConvTranspose2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_in', nonlinearity='leaky_relu')

    def forward(self, x):
        blocks = []
        for i, down in enumerate(self.down_path):
            x = down(x)
            if i != len(self.down_path) - 1:
                blocks.append(x)
                x = F.max_pool2d(x, 2)

        for i, up in enumerate(self.up_path):
            x = up(x, blocks[-i - 1])

        return self.last(x)

# Cell
_MODEL_BASE_URL = 'https://github.com/matjesg/deepflash2/releases/download/model_library/'
def _load_pretrained(model, dataset, progress):
    "Loads pretrained model weights"
    url = _MODEL_BASE_URL+dataset+'.pth'
    try:
        state_dict = torch.hub.load_state_dict_from_url(url, map_location='cpu', progress=progress)
    except:
        print(f"Error: No weights available for model trained on {dataset}.")

    if model.state_dict()['last.weight'].shape != state_dict['last.weight'].shape:
        print(f"No pretrained weights for {model.state_dict()['last.weight'].shape[0]} classes in final layer.")
        state_dict.pop('last.bias')
        state_dict.pop('last.weight')


    # TODO Better handle different number of input channels
    _ = model.load_state_dict(state_dict, strict=False)
    #print(f"Loaded model weights trained on {dataset}.")

# Cell
def unet_ronneberger2015(in_channels=1 ,n_classes=2, pretrained=False, dataset='wue1_cFOS', progress=True):
    "Original U-Net architecture based on Ronnberger et al. (2015)"
    model = UNet2D(in_channels=in_channels, n_classes=n_classes,
                   depth=5, wf=6, padding=False, batch_norm=False,
                   neg_slope=0., up_mode='upconv', dropout=0)
    if pretrained:
        _load_pretrained(model, dataset, progress)
    return model

# Cell
def unet_falk2019(in_channels=1 ,n_classes=2, pretrained=False, dataset='wue1_cFOS', progress=True):
    "U-Net architecture based on Falk et al. (2019)"
    model = UNet2D(in_channels=in_channels, n_classes=n_classes,
               depth=5, wf=6, padding=False, batch_norm=False,
               neg_slope=0.1, up_mode='upconv', dropout=0)
    if pretrained:
        _load_pretrained(model, dataset, progress)
    return model

# Cell
def unet_deepflash2(in_channels=1 ,n_classes=2, pretrained=False, dataset='wue1_cFOS', progress=True, dropout=.5):
    "U-Net model optimized for deepflash2"
    model = UNet2D(in_channels=in_channels, n_classes=n_classes, dropout=dropout,
                   depth=5, wf=6, padding=False, batch_norm=True,
                   neg_slope=0.1, up_mode='upconv', )
    if pretrained:
        _load_pretrained(model, dataset, progress)
    return model

# Cell
def unet_custom(in_channels=1 ,n_classes=2, pretrained=False, progress=True, **kwargs):
    "Customizable U-Net model. Customize via kwargs"
    model = UNet2D(in_channels=in_channels, n_classes=n_classes, **kwargs)
    if pretrained:
        print('No pretrained weights available for custom architecture.')
    return model