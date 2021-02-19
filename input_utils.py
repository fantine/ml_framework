import tensorflow as tf

from trainer import utils


def _parse_function(example_proto, mode, input_shape, label_shape,
                    tfrecord_shape):
  keys_to_features = {'inputs': tf.io.FixedLenFeature([], tf.string)}
  if mode != tf.estimator.ModeKeys.PREDICT:
    keys_to_features['labels'] = tf.io.FixedLenFeature([], tf.string)

  parsed_example = tf.io.parse_example(example_proto, keys_to_features)
  inputs = tf.io.decode_raw(parsed_example['inputs'], tf.float32)
  inputs = tf.reshape(inputs, tfrecord_shape)

  if tfrecord_shape != input_shape:
    inputs = utils.random_crop(inputs, input_shape)

  if mode == tf.estimator.ModeKeys.PREDICT:
    return inputs

  labels = tf.io.decode_raw(parsed_example['labels'], tf.float32)
  labels = tf.reshape(labels, label_shape)
  return inputs, labels


def _get_dataset(
    file_pattern,
    input_shape,
    label_shape,
    tfrecord_shape,
    batch_size,
    mode=tf.estimator.ModeKeys.TRAIN,
    num_epochs=1,
    compression_type=None,
    shuffle=True,
    shuffle_buffer_size=10000
):
  dataset = tf.data.Dataset.list_files(file_pattern, shuffle=shuffle)
  dataset = dataset.interleave(
      lambda x: tf.data.TFRecordDataset(
          x, compression_type=compression_type),
      num_parallel_calls=tf.data.experimental.AUTOTUNE)
  dataset = dataset.prefetch(buffer_size=tf.data.experimental.AUTOTUNE)
  dataset = dataset.map(
      lambda x: _parse_function(
          x, mode, input_shape, label_shape, tfrecord_shape),
      num_parallel_calls=tf.data.experimental.AUTOTUNE)
  if shuffle:
    dataset = dataset.shuffle(shuffle_buffer_size)
  dataset = dataset.batch(batch_size)
  dataset = dataset.prefetch(buffer_size=tf.data.experimental.AUTOTUNE)
  return dataset


def get_input_shape(hparams):
  if hparams.depth == 1:
    if hparams.width == 1:
      return (hparams.height, hparams.channels)
    return (hparams.height, hparams.width, hparams.channels)
  return (hparams.height, hparams.width, hparams.depth, hparams.channels)


def get_label_shape(hparams):
  if hparams.label_depth == 1:
    if hparams.label_width == 1:
      return (hparams.label_height,)
    return (hparams.label_height, hparams.label_width)
  return (hparams.label_height, hparams.label_width, hparams.label_depth)


def get_tfrecord_shape(hparams):
  if hparams.tfrecord_height == -1:
    return get_input_shape(hparams)
  if hparams.tfrecord_depth == 1:
    if hparams.tfrecord_width == 1:
      return (hparams.tfrecord_height, hparams.channels)
    return (hparams.tfrecord_height, hparams.tfrecord_width, hparams.channels)
  return (hparams.tfrecord_height, hparams.tfrecord_width,
          hparams.tfrecord_depth, hparams.channels)


def get_dataset(hparams, mode):
  if mode == tf.estimator.ModeKeys.TRAIN:
    file_pattern = hparams.train_file
    shuffle = True
    num_epochs = hparams.num_epochs
  elif mode == tf.estimator.ModeKeys.EVAL:
    file_pattern = hparams.eval_file
    shuffle = False
    num_epochs = 1
  else:
    raise NotImplementedError('Unsupported mode {}'.format(mode))

  return _get_dataset(
      file_pattern,
      get_input_shape(hparams),
      get_label_shape(hparams),
      get_tfrecord_shape(hparams),
      hparams.batch_size,
      mode=mode,
      num_epochs=num_epochs,
      compression_type=hparams.compression_type,
      shuffle=shuffle,
      shuffle_buffer_size=hparams.shuffle_buffer_size)


def get_streaming_data(hparams):
  input_shape = get_input_shape(hparams)
  if len(input) == 3:
    _get_2d_streaming_data(hparams, input_shape)
  raise NotImplementedError('Only 2D streaming data supported for now.')


def _get_2d_streaming_data(hparams, input_shape):
  data = np.load(hparams.test_file)
  n1, n2 = data.shape[0], data.shape[1]
  w1, w2, _ = input_shape
  d1 = int((1. - hparams.overlap) * w1)
  d2 = int((1. - hparams.overlap) * w2)

  def _generator():
    for i1 in range(0, n1 - w1 + 1, d1):
      for i2 in range(0, n2 - w2 + 1, d2):
        yield data[i1:i1 + w1, i2:i2 + w2].reshape(input_shape)

  dataset = tf.data.Dataset.from_generator(
      generator, tf.float32, tf.TensorShape(input_shape))

  return dataset.batch(hparams.batch_size)
