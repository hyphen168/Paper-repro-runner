import torch
from torch import nn
from torch.nn import functional as F


class LossFunction:
    def __init__(self, reduction='mean'):
        self.loss_fn = nn.CrossEntropyLoss(reduction=reduction)

    def __call__(self, predictions, targets):
        return self.loss_fn(predictions, targets)


class CrossEntropyLoss(nn.Module):
    def __init__(self, weight=None, reduction='mean'):
        super().__init__()
        self.loss = nn.CrossEntropyLoss(weight=weight, reduction=reduction)

    def forward(self, inputs, targets):
        return self.loss(inputs, targets)


class FocalLoss(nn.Module):
    def __init__(self, alpha=1.0, gamma=2.0, reduction='mean'):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, inputs, targets):
        log_prob = F.log_softmax(inputs, dim=1)
        prob = torch.exp(log_prob)
        target_log_prob = -log_prob.gather(1, targets.unsqueeze(1)).squeeze(1)
        p_t = prob.gather(1, targets.unsqueeze(1)).squeeze(1)
        alpha_factor = self.alpha * (1 - p_t) ** self.gamma
        loss = alpha_factor * target_log_prob
        if self.reduction == 'mean':
            return loss.mean()
        if self.reduction == 'sum':
            return loss.sum()
        return loss


class DiceLoss(nn.Module):
    def __init__(self, smooth=1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, inputs, targets):
        inputs = torch.sigmoid(inputs)
        intersection = (inputs * targets).sum()
        dice = (2.0 * intersection + self.smooth) / (inputs.sum() + targets.sum() + self.smooth)
        return 1.0 - dice
