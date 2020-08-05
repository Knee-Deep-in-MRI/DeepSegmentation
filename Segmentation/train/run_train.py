import tensorflow as tf
from time import time
import os

from Segmentation.train.train import Trainer
from Segmentation.train.utils import Metric
from Segmentation.train.validation import validate_best_model

from Segmentation.utils.accelerator import setup_accelerator
from Segmentation.utils.data_loader import load_dataset
from Segmentation.utils.training_utils import LearningRateSchedule
from Segmentation.utils.losses import tversky_loss, dice_coef_loss, focal_tversky, weighted_cat_cross_entropy
from Segmentation.utils.metrics import dice_coef, mIoU

# Too many arguments in a function
def main(epochs,
         name,
         log_dir_now=None,
         batch_size=32,
         val_batch_size=32,
         lr=1e-4,
         lr_drop=0.9,
         lr_drop_freq=5,
         lr_warmup=3,
         num_to_visualise=2,
         num_channels=[4, 8, 16],
         buffer_size=1000,
         run_eager=True,
         tfrec_dir='./Data/tfrecords/',
         multi_class=False,
         crop_size=288,
         depth_crop_size=None,
         aug=[],
         use_2d=True,
         debug=False,
         predict_slice=False,
         tpu_name=None,
         num_cores=8,
         min_lr=1e-7,
         custom_loss=None,
         use_bfloat16=False,
         use_RGB=False,
         **model_kwargs,
         ):

    t0 = time()

    # set up accelerator and returns strategy used
    strategy = setup_accelerator(use_gpu=False if tpu_name is None else True,
                                 num_cores=num_cores,
                                 device_name=tpu_name)

    # load dataset
    train_ds, valid_ds = load_dataset(batch_size=batch_size,
                                      dataset_dir=tfrec_dir,
                                      augmentation=aug,
                                      use_2d=use_2d,
                                      multi_class=multi_class,
                                      crop_size=crop_size,
                                      buffer_size=buffer_size,
                                      use_bfloat16=use_bfloat16,
                                      use_RGB=use_RGB
                                      )

    # This shouldn't be hard-coded. Edit load_dataset to return number of classes used.
    num_classes = 7 if multi_class else 1

    # metrics shouldn't be hard-coded
    # Why do loss lists have 5 arugments???
    if multi_class:
        metrics = {
            'losses': {
                'dice': [dice_coef, tf.keras.metrics.Mean(), tf.keras.metrics.Mean(), None, None],
                'mIoU': [mIoU, tf.keras.metrics.Mean(), tf.keras.metrics.Mean(), None, None]
            }
        }

    with strategy.scope():
        if custom_loss is None:
            loss_func = tversky_loss if multi_class else dice_coef_loss
        elif multi_class and custom_loss == "weighted":
            loss_func = weighted_cat_cross_entropy
        elif multi_class and custom_loss == "focal":
            loss_func = focal_tversky
        else:
            raise NotImplementedError(f"Custom loss: {custom_loss} not implemented.")
        
        # rewrite a function that takes in model-specific arguments and returns model_fn
        # model = build_model(num_channels, num_classes, name, predict_slice=predict_slice, **model_kwargs)
        
        batch_size = batch_size * num_cores

        # Fix hard-coding ad check that the lr_drop_freq is a list, not int
        lr = LearningRateSchedule(19200 // batch_size, lr, min_lr, lr_drop, lr_drop_freq, lr_warmup)
        optimizer = tf.keras.optimizers.Adam(learning_rate=lr)

        trainer = Trainer(epochs,
                          batch_size,
                          run_eager,
                          model,
                          optimizer,
                          loss_func,
                          predict_slice,
                          metrics,
                          tfrec_dir=tfrec_dir)

        train_ds = strategy.experimental_distribute_dataset(train_ds)
        valid_ds = strategy.experimental_distribute_dataset(valid_ds)

        if log_dir_now is None:
            log_dir_now = trainer.train_model_loop(train_ds, valid_ds, strategy, multi_class, debug, num_to_visualise)

    train_time = time() - t0
    print(f"Train Time: {train_time:.02f}")
    t1 = time()
    with strategy.scope():
        model = build_model(num_channels, num_classes, name, predict_slice=predict_slice, **model_kwargs)
        model.load_weights(os.path.join(log_dir_now + '/best_weights.tf')).expect_partial()
    print("Validation for:", log_dir_now)

    if not predict_slice:
        total_loss, metric_str = validate_best_model(model,
                                                     log_dir_now,
                                                     val_batch_size,
                                                     buffer_size,
                                                     tfrec_dir,
                                                     multi_class,
                                                     crop_size,
                                                     depth_crop_size,
                                                     predict_slice,
                                                     Metric(metrics))
        print(f"Train Time: {train_time:.02f}")
        print(f"Validation Time: {time() - t1:.02f}")
        print(f"Total Time: {time() - t0:.02f}")
        with open("results/3d_result.txt", "a") as f:
            f.write(f'{log_dir_now}: total_loss {total_loss} {metric_str} \n')


if __name__ == "__main__":
    use_tpu = False

    with open("results/3d_result.txt", "a") as f:
        f.write(f'========================================== \n')

    debug = False
    es = 300

    # main(epochs=es, name='vnet-slice-aug', lr=1e-5, dropout_rate=1e-5, use_spatial_dropout=False, use_batchnorm=False, noise=1e-5,
    #      crop_size=128, depth_crop_size=2, num_channels=32, lr_drop_freq=8,
    #      num_conv_layers=3, batch_size=6, val_batch_size=4, multi_class=False, kernel_size=(3, 5, 5),
    #      aug=['shift', 'flip', 'rotate'], use_transpose=False, debug=debug, tpu=use_tpu, predict_slice=True, strides=(1, 2, 2), slice_format="sum")

    main(epochs=es, name='vnet-aug', lr=1e-4, dropout_rate=1e-5, use_spatial_dropout=False, use_batchnorm=False, noise=1e-5,
         crop_size=32, depth_crop_size=32, num_channels=1, lr_drop_freq=10,
         num_conv_layers=3, batch_size=2, val_batch_size=2, multi_class=False, kernel_size=(3, 3, 3),
         aug=['shift'], use_transpose=False, debug=debug, tpu=use_tpu)