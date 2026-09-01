import pytest

from industrial_vision.utils.metrics import calculate_accuracy, calculate_precision, calculate_recall


@pytest.mark.parametrize(
    ('y_true', 'y_pred', 'expected_accuracy', 'expected_precision', 'expected_recall'),
    [
        ([1, 0, 1, 1, 0], [1, 0, 1, 0, 0], 0.8, 1.0, 2/3),
        ([0, 1, 0, 1], [0, 0, 1, 1], 0.5, 0.5, 0.5),
    ],
)
def test_metrics(y_true, y_pred, expected_accuracy, expected_precision, expected_recall):
    assert calculate_accuracy(y_true, y_pred) == pytest.approx(expected_accuracy)
    assert calculate_precision(y_true, y_pred) == pytest.approx(expected_precision)
    assert calculate_recall(y_true, y_pred) == pytest.approx(expected_recall)
