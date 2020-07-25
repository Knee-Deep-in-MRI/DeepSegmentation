import tensorflow as tf
import tensorflow.keras.layers as tfkl
from Segmentation.model.unet_build_blocks import Conv_Block, Up_Conv

class Conv_ResBlock(tf.keras.Model):
    def __init__(self,
                 num_channels,
                 use_2d=False,
                 num_conv_layers=2,
                 kernel_size=3,
                 strides=2,
                 res_activation='relu',
                 data_format='channels_last',
                 **kwargs):

        super(Conv_ResBlock, self).__init__(**kwargs)

        self.num_channels = num_channels
        self.use_2d = use_2d
        self.num_conv_layers = num_conv_layers
        self.kernel_size = kernel_size
        self.strides = strides
        self.res_activation = res_activation
        self.data_format = data_format

        self.conv_block = Conv_Block(num_channels=self.num_channels,
                                     use_2d=self.use_2d,
                                     num_conv_layers=self.num_conv_layers,
                                     kernel_size=self.kernel_size,
                                     data_format=self.data_format,
                                     **kwargs)
        if self.use_2d:
            self.conv_stride = tfkl.Conv2D(num_channels * 2,
                                           kernel_size=(2, 2),
                                           strides=strides,
                                           padding='same')

        else:
            self.conv_stride = tfkl.Conv3D(num_channels * 2,
                                           kernel_size=(2, 2, 2),
                                           strides=strides,
                                           padding='same')
        if res_activation == 'prelu':
            self.res_activation = tfkl.PReLU()
        else:
            self.res_activation = tfkl.Activation(res_activation)

    def call(self, inputs, training):
        x = inputs
        x = self.conv_block(x, training=training)
        x = tfkl.add([x, inputs])
        down_x = self.conv_stride(x)
        down_x = self.res_activation(down_x)
        return down_x, x

class Up_ResBlock(tf.keras.Model):
    def __init__(self,
                 num_channels,
                 use_2d=False,
                 kernel_size=3,
                 **kwargs):
        super(Up_ResBlock, self).__init__(**kwargs)

        self.num_channels = num_channels
        self.use_2d = use_2d
        self.kernel_size = kernel_size
        self.up_conv = Up_Conv(num_channels=self.num_channels,
                               use_2d=self.use_2d,
                               kernel_size=self.kernel_size,
                               **kwargs)

    def call(self, inputs, training):
        x, x_highway = inputs
        x_res_start = self.up_conv(x, x_highway, training=training)
        x = tfkl.add([x, x_res_start])
        return x
