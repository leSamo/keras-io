"""
Title: Classification with TensorFlow Decision Forests
Author: [Khalid Salama](https://www.linkedin.com/in/khalid-salama-24403144/)
Date created: 2022/01/25
Last modified: 2022/01/25
Description: Using TensorFlow Decision Forests for structured data classification.
"""

"""
## Introduction

[TensorFlow Decision Forests](https://www.tensorflow.org/decision_forests)
is a collection of state-of-the-art algorithms of Decision Forest models
that are compatible with Keras APIs.
The models include [Random Forests](https://www.tensorflow.org/decision_forests/api_docs/python/tfdf/keras/RandomForestModel),
[Gradient Boosted Trees](https://www.tensorflow.org/decision_forests/api_docs/python/tfdf/keras/GradientBoostedTreesModel),
and [CART](https://www.tensorflow.org/decision_forests/api_docs/python/tfdf/keras/CartModel),
and can be used for regression, classification, and ranking task.

This example uses Gradient Boosted Trees model in binary classification of
structured data, and covers the following scenarios:

1. Build a decision forests model by specifying the input feature usage.
2. Implement a custom *Binary Target encoder* as a [Keras Preprocessing layer](https://keras.io/api/layers/preprocessing_layers/)
to encode the categorical features with respect to their target value co-occurrences,
and then use the encoded features to build a decision forests model.
3. Encode the categorical features as [embeddings](https://keras.io/api/layers/core_layers/embedding),
train these embeddings in a simple linear model, and then use the
trained embeddings as inputs to build decision forests model.

This example uses TensorFlow 2.7 or higher,
as well as [TensorFlow Decision Forests](https://www.tensorflow.org/decision_forests),
which you can install using the following command:

```python
pip install -U tensorflow_decision_forests
```
"""

"""
## Setup
"""

import math
import urllib
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import tensorflow_decision_forests as tfdf

"""
## Prepare the data

This example uses the
[United States Census Income Dataset](https://archive.ics.uci.edu/ml/datasets/Census-Income+%28KDD%29)
provided by the [UC Irvine Machine Learning Repository](https://archive.ics.uci.edu/ml/index.php).
The task is binary classification to determine whether a person makes over 50K a year.

The dataset includes ~300K instances with 41 input features: 7 numerical features
and 34 categorical features.

First we load the data from the UCI Machine Learning Repository into a Pandas DataFrame.
"""

BASE_PATH = "https://archive.ics.uci.edu/ml/machine-learning-databases/census-income-mld/census-income"
CSV_HEADER = [
    l.decode("utf-8").split(":")[0].replace(" ", "_")
    for l in urllib.request.urlopen(f"{BASE_PATH}.names")
    if not l.startswith(b"|")
][2:]
CSV_HEADER.append("income_level")

train_data = pd.read_csv(f"{BASE_PATH}.data.gz", header=None, names=CSV_HEADER,)
test_data = pd.read_csv(f"{BASE_PATH}.test.gz", header=None, names=CSV_HEADER,)

"""
We convert the target column from string to integer.
"""

target_labels = [" - 50000.", " 50000+."]
train_data["income_level"] = train_data["income_level"].map(target_labels.index)
test_data["income_level"] = test_data["income_level"].map(target_labels.index)

"""
Now let's show the shapes of the training and test dataframes, and display some instances.
"""

print(f"Train data shape: {train_data.shape}")
print(f"Test data shape: {test_data.shape}")
print(train_data.head().T)

"""
## Define dataset metadata

Here, we define the metadata of the dataset that will be useful for encoding
the input features with respect to their types.
"""

# Target column name.
TARGET_COLUMN_NAME = "income_level"
# Weight column name.
WEIGHT_COLUMN_NAME = "instance_weight"
# Numeric feature names.
NUMERIC_FEATURE_NAMES = [
    "age",
    "wage_per_hour",
    "capital_gains",
    "capital_losses",
    "dividends_from_stocks",
    "num_persons_worked_for_employer",
    "weeks_worked_in_year",
]
# Categorical features and their vocabulary lists.
CATEGORICAL_FEATURES_WITH_VOCABULARY = {
    feature_name: sorted(
        [str(value) for value in list(train_data[feature_name].unique())]
    )
    for feature_name in CSV_HEADER
    if feature_name
    not in list(NUMERIC_FEATURE_NAMES + [WEIGHT_COLUMN_NAME, TARGET_COLUMN_NAME])
}
# All features names.
FEATURE_NAMES = NUMERIC_FEATURE_NAMES + list(
    CATEGORICAL_FEATURES_WITH_VOCABULARY.keys()
)

"""
## Configure hyperparameters

You can find all the parameters of the Gradient Boosted Tree model in the
[documentation](https://www.tensorflow.org/decision_forests/api_docs/python/tfdf/keras/GradientBoostedTreesModel)
"""

GROWING_STRATEGY = "BEST_FIRST_GLOBAL"
NUM_TREES = 250
MIN_EXAMPLES = 6
MAX_DEPTH = 5
SUBSAMPLE = 0.65
SAMPLING_METHOD = "RANDOM"
VALIDATION_RATIO = 0.1

"""
## Implement a training and evaluation procedure
"""


def prepare_sample(features, target, weight):
    for feature_name in features:
        if feature_name in CATEGORICAL_FEATURES_WITH_VOCABULARY:
            if features[feature_name].dtype != tf.dtypes.string:
                # Convert categorical feature values to string.
                features[feature_name] = tf.strings.as_string(features[feature_name])
    return features, target, weight


def run_experiment(model, train_data, test_data, num_epochs=1, batch_size=None):

    train_dataset = tfdf.keras.pd_dataframe_to_tf_dataset(
        train_data, label=TARGET_COLUMN_NAME, weight=WEIGHT_COLUMN_NAME
    ).map(prepare_sample, num_parallel_calls=tf.data.AUTOTUNE)
    test_dataset = tfdf.keras.pd_dataframe_to_tf_dataset(
        test_data, label=TARGET_COLUMN_NAME, weight=WEIGHT_COLUMN_NAME
    ).map(prepare_sample, num_parallel_calls=tf.data.AUTOTUNE)

    model.fit(train_dataset, epochs=num_epochs, batch_size=batch_size)
    _, accuracy = model.evaluate(test_dataset, verbose=0)
    print(f"Test accuracy: {round(accuracy * 100, 2)}%")


"""
## Create model inputs
"""


def create_model_inputs():
    inputs = {}
    for feature_name in FEATURE_NAMES:
        if feature_name in NUMERIC_FEATURE_NAMES:
            inputs[feature_name] = layers.Input(
                name=feature_name, shape=(), dtype=tf.float32
            )
        else:
            inputs[feature_name] = layers.Input(
                name=feature_name, shape=(), dtype=tf.string
            )
    return inputs


"""
## Experiment 1: Decision Forests with raw features
"""

"""
### Specify model input feature usages

You can attach semantics to each feature to control how it is used by the model.
If not specified, the semantics are inferred from the representation type.
It is recommended to specify the [feature usages](https://www.tensorflow.org/decision_forests/api_docs/python/tfdf/keras/FeatureUsage)
explicitly to avoid incorrect inferred semantics is incorrect.
For example, a categorical value identifier (integer) will be be inferred as numerical,
while it is semantically categorical.

For numerical features, you can set the `discretized` parameters to the number
of buckets by which the numerical feature should be discretized.
This makes the training faster but may lead to worse models.
"""


def specify_feature_usages(inputs):
    feature_usages = []

    for feature_name in inputs:
        if inputs[feature_name].dtype == tf.dtypes.float32:
            feature_usage = tfdf.keras.FeatureUsage(
                name=feature_name, semantic=tfdf.keras.FeatureSemantic.NUMERICAL
            )
        else:
            feature_usage = tfdf.keras.FeatureUsage(
                name=feature_name, semantic=tfdf.keras.FeatureSemantic.CATEGORICAL
            )

        feature_usages.append(feature_usage)
    return feature_usages


"""
### Create a Gradient Boosted Trees model

When compiling a decision forests model, you may only provide extra evaluation metrics.
The loss is specified in the model construction,
and the optimizer is irrelevant to decision forests models.
"""


def create_gbt_model():
    gbt_model = tfdf.keras.GradientBoostedTreesModel(
        features=specify_feature_usages(create_model_inputs()),
        exclude_non_specified_features=True,
        growing_strategy=GROWING_STRATEGY,
        num_trees=NUM_TREES,
        max_depth=MAX_DEPTH,
        min_examples=MIN_EXAMPLES,
        subsample=SUBSAMPLE,
        validation_ratio=VALIDATION_RATIO,
        task=tfdf.keras.Task.CLASSIFICATION,
        loss="DEFAULT",
    )

    gbt_model.compile(metrics=[keras.metrics.BinaryAccuracy(name="accuracy")])
    return gbt_model


"""
### Train and evaluate the model

Note that when training a Decision Forests model, only one epoch is needed to
read the full dataset. Any extra steps will result in unnecessary slower training.
Therefore, the default `num_epochs=1` is used in the `run_experiment` method.
"""

gbt_model = create_gbt_model()
run_experiment(gbt_model, train_data, test_data)

"""
### Inspect the model

The `model.summary()` method will display several types of information about
your decision trees model, model type, task, input features, and feature importance.
"""

print(gbt_model.summary())

"""
## Experiment 2: Decision Forests with target encoding

[Target encoding](https://dl.acm.org/doi/10.1145/507533.507538) is a common preprocessing
technique for categorical features that convert them into numerical features.
Using categorical features with high cardinality as-is may lead to overfitting.
Target encoding aims to replace each categorical feature value with one or more
numerical values that represent its co-occurrence with the target labels.

More precisely, given a categorical feature, the binary target encoder in this example
will produce three new numerical features:

1. `positive_frequency`: How many times each feature value occurred with a positive target label.
2. `negative_frequency`: How many times each feature value occurred with a negative target label.
3. `positive_probability`: The probability that the target label is positive,
given the feature value, which is computed as
`positive_frequency / (positive_frequency + negative_frequency)`.


Note that target encoding is effective with models that cannot automatically
learn dense representations to categorical features, such as decision forests
or kernel methods. If neural network models are used, its recommended to
encode categorical features as embeddings.
"""

"""
### Implement Binary Target Encoder

For simplicity, we assume that the inputs for the `adapt` and `call` methods
are in the expected data types and shapes, so no validation logic is added.
"""


class BinaryTargetEncoding(layers.Layer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def adapt(self, data):
        # data is expected to be an integer numpy array to a Tensor shape [num_exmples, 2].
        # This contains feature values for a given feature in the dataset, and target values.

        # Convert the data to a tensor.
        data = tf.convert_to_tensor(data)
        # Separate the feature values and target values
        feature_values = tf.cast(data[:, 0], tf.dtypes.int64)
        target_values = tf.cast(data[:, 1], tf.dtypes.bool)

        print("Target encoding: Computing unique feature values...")
        # Get feature vocabulary.
        unique_feature_values = tf.sort(tf.unique(feature_values).y)

        print(
            "Target encoding: Computing frequencies for feature values with positive targets..."
        )
        # Filter the data where the target label is positive.
        positive_indices = tf.where(condition=target_values)
        postive_feature_values = tf.gather_nd(
            params=feature_values, indices=positive_indices
        )
        # Compute how many times each feature value occurred with a positive target label.
        positive_frequency = tf.math.unsorted_segment_sum(
            data=tf.ones(
                shape=(postive_feature_values.shape[0], 1), dtype=tf.dtypes.int32
            ),
            segment_ids=postive_feature_values,
            num_segments=unique_feature_values.shape[0],
        )

        print(
            "Target encoding: Computing frequencies for feature values with negative targets..."
        )
        # Filter the data where the target label is negative.
        negative_indices = tf.where(condition=tf.math.logical_not(target_values))
        negative_feature_values = tf.gather_nd(
            params=feature_values, indices=negative_indices
        )
        # Compute how many times each feature value occurred with a negative target label.
        negative_frequency = tf.math.unsorted_segment_sum(
            data=tf.ones(
                shape=(negative_feature_values.shape[0], 1), dtype=tf.dtypes.int32
            ),
            segment_ids=negative_feature_values,
            num_segments=unique_feature_values.shape[0],
        )

        print("Target encoding: Storing target encoding statistics...")
        self.positive_frequency_lookup = tf.constant(positive_frequency)
        self.negative_frequency_lookup = tf.constant(negative_frequency)

    def reset_state(self):
        self.positive_frequency_lookup = None
        self.negative_frequency_lookup = None

    def call(self, inputs):
        # inputs is expected to be an integer numpy array to a Tensor shape [num_exmples, 1].
        # This includes the feature values for a given feature in the dataset.

        # Raise an error if the target encoding statistics are not computed.
        if (
            self.positive_frequency_lookup == None
            or self.negative_frequency_lookup == None
        ):
            raise ValueError(
                f"You need to call the adapt method to compute target encoding statistics."
            )

        # Convert the inputs to a tensor.
        inputs = tf.convert_to_tensor(inputs)
        # Cast the inputs int64 a tensor.
        inputs = tf.cast(inputs, tf.dtypes.int64)
        # Lookup positive frequencies for the input feature values.
        positive_fequency = tf.cast(
            tf.gather_nd(self.positive_frequency_lookup, inputs),
            dtype=tf.dtypes.float32,
        )
        # Lookup negative frequencies for the input feature values.
        negative_fequency = tf.cast(
            tf.gather_nd(self.negative_frequency_lookup, inputs),
            dtype=tf.dtypes.float32,
        )
        # Compute positive probability for the input feature values.
        positive_probability = positive_fequency / (
            positive_fequency + negative_fequency
        )
        # Concatenate and return the looked-up statistics.
        return tf.concat(
            [positive_fequency, negative_fequency, positive_probability], axis=1
        )


"""
Let's test the binary target encoder
"""

data = tf.constant(
    [
        [0, 1],
        [2, 0],
        [0, 1],
        [1, 1],
        [1, 1],
        [2, 0],
        [1, 0],
        [0, 1],
        [2, 1],
        [1, 0],
        [0, 1],
        [2, 0],
        [0, 1],
        [1, 1],
        [1, 1],
        [2, 0],
        [1, 0],
        [0, 1],
        [2, 0],
    ]
)

binary_target_encoder = BinaryTargetEncoding()
binary_target_encoder.adapt(data)
print(binary_target_encoder([[0], [1], [2]]))

"""
### Implement a feature encoding with target encoding
"""


def create_target_encoder():
    inputs = create_model_inputs()
    target_values = train_data[[TARGET_COLUMN_NAME]].to_numpy()
    encoded_features = []
    for feature_name in inputs:
        if feature_name in CATEGORICAL_FEATURES_WITH_VOCABULARY:
            vocabulary = CATEGORICAL_FEATURES_WITH_VOCABULARY[feature_name]
            # Create a lookup to convert string values to an integer indices.
            # Since we are not using a mask token nor expecting any out of vocabulary
            # (oov) token, we set mask_token to None and  num_oov_indices to 0.
            lookup = layers.StringLookup(
                vocabulary=vocabulary, mask_token=None, num_oov_indices=0
            )
            # Convert the string input values into integer indices.
            value_indices = lookup(inputs[feature_name])
            # Prepare the data to adapt the target encoding.
            print("### Adapting target encoding for:", feature_name)
            feature_values = train_data[[feature_name]].to_numpy().astype(str)
            feature_value_indices = lookup(feature_values)
            data = tf.concat([feature_value_indices, target_values], axis=1)
            feature_encoder = BinaryTargetEncoding()
            feature_encoder.adapt(data)
            # Convert the feature value indices to target encoding representations.
            encoded_feature = feature_encoder(tf.expand_dims(value_indices, -1))
        else:
            # Expand the dimensions of the numerical input feature and use it as-is.
            encoded_feature = tf.expand_dims(inputs[feature_name], -1)
        # Add the encoded feature to the list.
        encoded_features.append(encoded_feature)
    # Concatenate all the encoded features.
    encoded_features = tf.concat(encoded_features, axis=1)
    # Create and return a Keras model with encoded features as outputs.
    return keras.Model(inputs=inputs, outputs=encoded_features)


"""
### Create a Gradient Boosted Trees model with a preprocessor

In this scenario, we use the target encoding as a preprocessor for the Gradient Boosted Tree model,
and let the model infer semantics of the input features.
"""


def create_gbt_with_preprocessor(preprocessor):

    gbt_model = tfdf.keras.GradientBoostedTreesModel(
        preprocessing=preprocessor,
        growing_strategy=GROWING_STRATEGY,
        num_trees=NUM_TREES,
        max_depth=MAX_DEPTH,
        min_examples=MIN_EXAMPLES,
        subsample=SUBSAMPLE,
        validation_ratio=VALIDATION_RATIO,
        task=tfdf.keras.Task.CLASSIFICATION,
    )

    gbt_model.compile(metrics=[keras.metrics.BinaryAccuracy(name="accuracy")])

    return gbt_model


"""
### Train and evaluate the model
"""

gbt_model = create_gbt_with_preprocessor(create_target_encoder())
run_experiment(gbt_model, train_data, test_data)

"""
## Experiment 3: Decision Forests with trained embeddings

In this scenario, we build an encoder model that codes the categorical
features to embeddings, where the size of the embedding for a given categorical
feature is the square root to the size of its vocabulary.

We train these embeddings in a simple linear model through backpropagation.
After the embedding encoder is trained, we used it as a preprocessor to the
input features of a Gradient Boosted Tree model.

Note that the embeddings and a decision forest model cannot be trained
synergically in one phase, since decision forest models do not train with backpropagation.
Rather, embeddings has to be trained in an initial phase,
and then used as static inputs to the decision forest model.
"""

"""
### Implement feature encoding with embeddings
"""


def create_embedding_encoder():
    inputs = create_model_inputs()
    encoded_features = []
    for feature_name in inputs:
        if feature_name in CATEGORICAL_FEATURES_WITH_VOCABULARY:
            vocabulary = CATEGORICAL_FEATURES_WITH_VOCABULARY[feature_name]
            # Create a lookup to convert string values to an integer indices.
            # Since we are not using a mask token nor expecting any out of vocabulary
            # (oov) token, we set mask_token to None and  num_oov_indices to 0.
            lookup = layers.StringLookup(
                vocabulary=vocabulary, mask_token=None, num_oov_indices=0
            )
            # Convert the string input values into integer indices.
            value_index = lookup(inputs[feature_name])
            # Create an embedding layer with the specified dimensions
            vocabulary_size = len(vocabulary)
            embedding_size = int(math.sqrt(vocabulary_size))
            feature_encoder = layers.Embedding(
                input_dim=len(vocabulary), output_dim=embedding_size
            )
            # Convert the index values to embedding representations.
            encoded_feature = feature_encoder(value_index)
        else:
            # Expand the dimensions of the numerical input feature and use it as-is.
            encoded_feature = tf.expand_dims(inputs[feature_name], -1)
        # Add the encoded feature to the list.
        encoded_features.append(encoded_feature)
    # Concatenate all the encoded features.
    encoded_features = layers.concatenate(encoded_features, axis=1)
    # Create and return a Keras model with encoded features as outputs.
    return keras.Model(inputs=inputs, outputs=encoded_features)


"""
### Build a linear model to train the embeddings
"""


def create_linear_model(encoder):
    inputs = create_model_inputs()
    embeddings = encoder(inputs)
    linear_output = layers.Dense(units=1, activation="sigmoid")(embeddings)

    linear_model = keras.Model(inputs=inputs, outputs=linear_output)
    linear_model.compile(
        optimizer=keras.optimizers.Adam(),
        loss=keras.losses.BinaryCrossentropy(),
        metrics=[keras.metrics.BinaryAccuracy("accuracy")],
    )
    return linear_model


embedding_encoder = create_embedding_encoder()
run_experiment(
    create_linear_model(embedding_encoder),
    train_data,
    test_data,
    num_epochs=3,
    batch_size=256,
)

"""
### Train and evaluate a Gradient Boosted Tree model with embeddings
"""

gbt_model = create_gbt_with_preprocessor(embedding_encoder)
run_experiment(gbt_model, train_data, test_data)

"""
## Concluding remarks

TensorFlow Decision Forests provide powerful models, especially with structured data.
In our experiments, the Gradient Boosted Tree model achieved 95.79% test accuracy.
When using the target encoding with categorical feature, the same model achieved 95.81% test accuracy.
When pretraining embeddings to be used as inputs to the Gradient Boosted Tree model,
we achieved 95.82% test accuracy.

Decision Forests can be used with Neural Networks, either by
1) using Neural Networks to learn useful representation of the input data,
and then using Decision Forests for the supervised learning task, or by
2) creating an ensemble of both Decision Forests and Neural Network models.

Note that TensorFlow Decision Forests does not (yet) support hardware accelerators.
All training and inference is done on the CPU.
Besides, Decision Forests require a finite dataset that fits in memory
for their training procedures. However, there are diminishing returns
for increasing the size of the dataset, and Decision Forests algorithms
arguably need fewer examples for convergence than large Neural Network models.
"""
