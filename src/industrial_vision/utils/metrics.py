import numpy as np


def _as_numpy_array(values):
    arr = np.asarray(values)
    return arr.reshape(-1)


def calculate_accuracy(y_true, y_pred):
    y_true = _as_numpy_array(y_true)
    y_pred = _as_numpy_array(y_pred)
    if y_true.shape[0] != y_pred.shape[0]:
        raise ValueError('y_true and y_pred must have the same length')
    correct = np.sum(y_true == y_pred)
    total = y_true.size
    return float(correct / total) if total > 0 else 0.0


def calculate_precision(y_true, y_pred):
    y_true = _as_numpy_array(y_true)
    y_pred = _as_numpy_array(y_pred)
    if y_true.shape[0] != y_pred.shape[0]:
        raise ValueError('y_true and y_pred must have the same length')
    true_positive = np.sum((y_true == 1) & (y_pred == 1))
    false_positive = np.sum((y_true == 0) & (y_pred == 1))
    denom = true_positive + false_positive
    return float(true_positive / denom) if denom > 0 else 0.0


def calculate_recall(y_true, y_pred):
    y_true = _as_numpy_array(y_true)
    y_pred = _as_numpy_array(y_pred)
    if y_true.shape[0] != y_pred.shape[0]:
        raise ValueError('y_true and y_pred must have the same length')
    true_positive = np.sum((y_true == 1) & (y_pred == 1))
    false_negative = np.sum((y_true == 1) & (y_pred == 0))
    denom = true_positive + false_negative
    return float(true_positive / denom) if denom > 0 else 0.0


def calculate_f1_score(y_true, y_pred):
    precision = calculate_precision(y_true, y_pred)
    recall = calculate_recall(y_true, y_pred)
    return float(2 * (precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0


def accuracy(y_true, y_pred):
    return calculate_accuracy(y_true, y_pred)


def precision(y_true, y_pred):
    return calculate_precision(y_true, y_pred)


def recall(y_true, y_pred):
    return calculate_recall(y_true, y_pred)


def f1_score(y_true, y_pred):
    return calculate_f1_score(y_true, y_pred)