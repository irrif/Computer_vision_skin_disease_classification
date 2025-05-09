from typing import Tuple, Union

from collections import defaultdict

import torch
from torch.utils.data import DataLoader
import torch.nn as nn
import torch.nn.functional as F

from torchvision.transforms.functional import adjust_contrast

from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score

import seaborn as sns
import matplotlib.pyplot as plt


class SmallNetwork(nn.Module):

    def __init__(self):
        super(SmallNetwork, self).__init__()
        self.conv1 = nn.Conv2d(in_channels=3, out_channels=16, kernel_size=(3, 3), stride=1, padding=0)
        self.act1 = nn.ReLU()

        self.conv2 = nn.Conv2d(in_channels=16, out_channels=64, kernel_size=(5, 5), stride=1, padding=0)
        self.act2 = nn.ReLU()

        self.pool1 = nn.MaxPool2d(kernel_size=(2, 2), stride=1, padding=0)

        self.conv3 = nn.Conv2d(in_channels=64, out_channels=128, kernel_size=(3, 3), stride=1, padding=0)
        self.act3 = nn.ReLU()

        self.pool2 = nn.MaxPool2d(kernel_size=(2, 2), stride=2, padding=0)

        self.flat = nn.Flatten()

        self.fc1 = nn.Linear(in_features=10_368, out_features=6_400)
        self.fc2 = nn.Linear(in_features=6_400, out_features=1_280)
        self.fc3 = nn.Linear(in_features=1_280, out_features=7)


    def forward(self, x):
        x = self.conv1(x)
        x = self.act1(x)

        x = self.conv2(x)
        x = self.act2(x)

        x = self.pool1(x)

        x = self.conv3(x)
        x = self.act3(x)

        x = self.pool2(x)

        x = torch.flatten(x, 1)

        x = self.fc1(x)
        x = F.relu(x)
        x = self.fc2(x)
        x = F.relu(x)
        x = self.fc3(x)
        output = F.log_softmax(x, dim=1)

        return output
    

class BasicBlock(nn.Module):
    def __init__(
            self,
            in_channels,
            out_channels,
            stride=1
        ):
        super(BasicBlock, self).__init__()

        # First block convolution
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

        # Second block convolution
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)

        # Shortcut connection
        self.shortcut = nn.Sequential()

        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels)
            )

    def forward(self, x):
        # Convolution 1
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)
        # Convolution 2
        out = self.conv2(out)
        out = self.bn2(out)
        # Shortcut connection
        out += self.shortcut(x) 
        out = self.relu(out)

        return out


class ResNet18(nn.Module):
    """
    Implement ResNet18 neural network architecture.
    """
    def __init__(
            self,
            num_classes: int = 7
        ):
        super(ResNet18, self).__init__()

        self.num_classes = num_classes
        self.in_channels = 64

        self.conv1 = nn.Conv2d(in_channels=3, out_channels=64, kernel_size=7, stride=2, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        self.layer1 = self._make_layer(
            block=BasicBlock,
            out_channels=64,
            n_blocks=2,
            stride=1
        )

        self.layer2 = self._make_layer(
            block=BasicBlock,
            out_channels=128,
            n_blocks=2,
            stride=2
        )

        self.layer3 = self._make_layer(
            block=BasicBlock,
            out_channels=256,
            n_blocks=2,
            stride=2
        )

        self.layer4 = self._make_layer(
            block=BasicBlock,
            out_channels=512,
            n_blocks=2,
            stride=2
        )

        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(in_features=512, out_features=num_classes)


    def _make_layer(self, block, out_channels, n_blocks, stride):
        strides = [stride] + [1] * (n_blocks - 1)
        layers = []
        for stride in strides:
            layers.append(block(self.in_channels, out_channels, stride))
            self.in_channels = out_channels
        return nn.Sequential(*layers)
    

    def forward(self, x):
        # ResNet first layer
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)
        out = self.maxpool(out)

        # 4 BasicBlock repeated twice
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)

        # Output layer
        out = self.avgpool(out)
        out = out.view(out.size(0), -1)
        out = self.fc(out)

        return out
    

class EarlyStopping():
    """
    Early stopping class.
    """
    def __init__(self, patience=5, delta=0):
        self.patience = patience
        self.delta = delta
        self.best_score = None
        self.early_stop = False
        self.counter = 0
        self.best_model_state = None
        self.epoch_stop = 0


    def __call__(
            self,
            val_loss: float,
            model: nn.Module,
            epoch: int
        ) -> None:

        score = -val_loss
        if self.best_score is None:
            self.best_score = score
            self.best_model_state = model.state_dict()

        # If score doesn't improve, add 1 to counter
        elif score < self.best_score + self.delta:
            self.counter += 1
            # If counter greater or equal than patience then early stop
            if self.counter >= self.patience:
                self.early_stop = True
                self.epoch_stop = epoch - self.patience

        else:
            self.best_score = score
            self.best_model_state = model.state_dict()
            self.counter = 0


    def load_best_model(self, model):
        """
        Load best model parameters.
        """
        model.load_state_dict(self.best_model_state)


def train_model(
        model: nn.Module, 
        device: torch.device,
        train_loader: DataLoader,
        loss_function: nn.functional,
        optimizer: torch.optim,
        epoch: int, 
        save: bool, 
        verbose: int
    ) -> Tuple[float]:
    """
    Train a model with the specified optimizer and loss function, over the number of epochs.
    Return loss and accuracy if save=True, otherwise return (0, 0).

    Parameters
    ----------
    model : pytorch model
        model to be trained
    device : torch.device
        Calculation device
    train_loader : torch.DataLoader
        Training DataLoader
    optimizer : torch.optim
        Optimizer
    loss_function : nn.functional
        Loss function
    epoch : int
        Number of epoch to train the model
    save : bool
        Set True to return the loss and accuracy history
    verbose : int
        Print loss and accuracy
        * 1 : For each n batches
        * 2 : For each n batches and for each epoch

    Returns
    -------
    (float, float)

    Example
    -------
    >>> model = ResNet18(num_classes=7)
    >>> device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    >>> train_dataloader = generate_dataloader(...)
    >>> optimizer = optim.Adam(model.parameters, lr=0.0001)
    >>> criterion = nn.CrossEntropyLoss()
    >>> n_epochs = 50
    >>> train_model(
    >>>     model=model,
    >>>     device=device,
    >>>     train_loader=train_dataloader
    >>>     optimizer=optimizer,
    >>>     loss_function=criterion,
    >>>     save=True,
    >>>     verbose=2
    >>> )
    """
    # Set model in training mode
    model.train()

    losses, corrects = [], 0

    for batch_idx, sample in enumerate(train_loader):
        # Sent data and label to specified device
        data, label = sample['image'].to(device), sample['label'].to(device)
        optimizer.zero_grad() # Set all gradients to 0
        y_pred = model(data)
        loss = loss_function(y_pred, label)
        # Saves batch loss in a list
        if save:
            losses.append(loss)

        loss.backward() # Backpropagation
        optimizer.step()

        # Count correct predictions
        preds = y_pred.argmax(dim=1, keepdim=True)
        corrects += preds.eq(label.view_as(preds)).sum().item()

        # Print loss every x batches
        if verbose >= 1:
            if batch_idx % 10 == 0:
                print("Train Epoch {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}".format(
                    epoch, batch_idx * len(data), len(train_loader.dataset),
                    100 * batch_idx * len(data) / len(train_loader.dataset), loss.item()
                ))
    # Compute epoch average train loss and train accuracy
    avg_loss = sum(losses) / len(losses)
    overall_accuracy = 100 * corrects / len(train_loader.dataset)

    # Print epoch average loss and accuracy
    if verbose == 2:
        print("\nTrain set : Average loss {:.4f}, Accuracy : {}/{} ({:.0f}%)".format(
            avg_loss, corrects, len(train_loader.dataset), overall_accuracy
        ))

    # Return epoch average loss and accuracy
    if save:
        return avg_loss, overall_accuracy
    else:
        return 0.0, 0.0


def validate_model(
        model: nn.Module, 
        device: torch.device,
        valid_loader: DataLoader,
        loss_function: nn.functional,
        save: bool, 
        verbose: bool
    ) -> Tuple[float]:
    """
    Compute loss and accuracy on validation set.
    Return loss and accuracy if save=True, otherwise return (0, 0).

    Parameters
    ----------
    model : nn.Module
        model to validate
    device : torch.device
        Calculation device
    valid_loader : torch.DataLoader
        Validation DataLoader
    loss_function : nn.functional
        Loss function
    save : bool
        Set True to return the loss and accuracy history
    verbose : bool
        Print loss and accuracy

    Returns
    -------
    (float, float)

        Example
    -------
    >>> device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    >>> model = ResNet18(num_classes=7).to(device)
    >>> valid_dataloader = generate_dataloader(...)
    >>> optimizer = optim.Adam(model.parameters, lr=0.0001)
    >>> criterion = nn.CrossEntropyLoss()
    >>> validate_model(
    >>>     model=model,
    >>>     device=device,
    >>>     valid_loader=valid_dataloader
    >>>     loss_function=criterion,
    >>>     save=True,
    >>>     verbose=True
    >>> )
    """
    model.to(device)

    val_losses, corrects = [], 0

    model.eval() # Set model in evaluation mode
    with torch.no_grad():
        for sample in valid_loader:
            # Sent data and label to specified device
            data, label = sample['image'].to(device), sample['label'].to(device)

            # Predict and compute loss
            y_pred = model(data)
            loss = loss_function(y_pred, label)

            # Save loss in a list
            if save:
                val_losses.append(loss)

            # Count correct predictions
            pred = y_pred.argmax(dim=1, keepdim=True)
            corrects += pred.eq(label.view_as(pred)).sum().item()

            # Print validation loss and accuracy
            avg_loss = sum(val_losses) / len(val_losses)
            size = len(valid_loader.dataset)
            accuracy = 100 *  corrects / size

        if verbose:
            print("\nValidation set : Average Loss: {:.4f}, Accuracy : {}/{} ({:.0f}%)\n".format(
                avg_loss, corrects, size, accuracy

            ))

    # Return epoch average loss and accuracy
    if save:
        return avg_loss, accuracy
    else:
        return 0.0, 0.0


def test_model(
        models: Union[nn.Module, list],
        device: torch.device,
        test_loader : DataLoader,
        verbose: bool
    ) -> dict:
    """
    Test the model and returns a dictionnary containing per-class precision, recall, F1-Score.\n
    But also overall acurracy, macro F1 score and average F1 score.\n
    And correct labels and true labels for each predictions


    Parameters
    ----------
    model : nn.Module
        model to be tested
    device : torch.device
        Calculation device
    test_loader : Dataloader
        Test Dataloader
    verbose : bool
        Set to True to print metrics

    Returns
    -------
    dict

    Example
    -------
    >>> device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    >>> model = ResNet18().to(device)
    >>> test_dataloader = generate_dataloader(...)
    >>> test_model(
    >>>     model=model,
    >>>     device=device,
    >>>     test_loader=test_dataloader,
    >>>     verbose=True
    >>> )
    """
    models = _ensure_model_list(models)
    for model in models:
        model.eval()

    num_classes = models[0].num_classes

    y_true_all, y_pred_all = [], []

    stats = _initialize_per_class_dict()

    with torch.no_grad():
        for sample in test_loader:
            test_data, test_label = sample['image'].to(device), sample['label'].to(device)

            logits = get_models_predictions(models, test_data)
            y_pred_test = torch.argmax(logits, dim=1) # prediction

            _update_per_class_dict(stats, y_pred_test, test_label)

            y_true_all.extend(test_label.cpu().tolist())
            y_pred_all.extend(y_pred_test.cpu().tolist())

            metrics = _finalize_metrics(
                stats, y_true_all, y_pred_all, test_loader, compute_classification_metrics, num_classes
            )

    if verbose:
        print("Test accuracy : {}/{} ({:.2f}%)".format(
            stats['correct_total'], len(test_loader.dataset), 
            metrics['overall_accuracy']
        ))

    return metrics


def _ensure_model_list(models):
    """ 
    Check if a list of models is provided or not.
    """
    return models if isinstance(models, (list, tuple)) else [models]


def get_models_predictions(models, input_tensor):
    """
    Predictions.
    """
    logits = [model(input_tensor) for model in models]
    return torch.mean(torch.stack(logits), dim=0)


def _initialize_per_class_dict():
    """
    Create a dictionnary that contains per class wrong, correct and total predictions.
    """
    return {
        'correct_total': 0,
        'total_per_class': defaultdict(int),
        'correct_per_class': defaultdict(int),
        'wrong_predictions': defaultdict(list),
        'predicted_as_class': defaultdict(int),
    }


def _update_per_class_dict(stats: dict, y_pred: torch.tensor, y_true: torch.tensor):
    """
    Compute per class total, correct and wrong predictions.
    """
    stats['correct_total'] += y_pred.eq(y_true).sum().item()

    for true_label, pred_label in zip(y_true, y_pred):
        true_label = true_label.item()
        pred_label = pred_label.item()

        stats['total_per_class'][true_label] += 1
        stats['predicted_as_class'][pred_label] += 1

        if true_label == pred_label:
            stats['correct_per_class'][true_label] += 1
        else:
            stats['wrong_predictions'][true_label].append(pred_label)


def _finalize_metrics(stats, y_true_all, y_pred_all, test_loader, compute_fn, num_classes):
    """
    Compute 
    """
    overall_accuracy = stats['correct_total'] / len(test_loader.dataset) * 100

    metrics = compute_fn(
        correct_per_class=stats['correct_per_class'],
        total_per_class=stats['total_per_class'],
        wrong_predictions=stats['wrong_predictions'],
        predicted_as_class=stats['predicted_as_class'],
        y_true=y_true_all,
        y_pred=y_pred_all,
        num_classes=num_classes
    )

    metrics['overall_accuracy'] = overall_accuracy
    metrics['correct_labels'] = y_true_all
    metrics['predicted_labels'] = y_pred_all

    return metrics


def compute_classification_metrics(
        correct_per_class: dict, 
        total_per_class: dict,
        wrong_predictions: dict, 
        predicted_as_class: dict, 
        y_true: list,
        y_pred: list,
        num_classes: int
    ) -> dict:
    """
    Compute Precision, Recall, and F1-Score for each class.

    Parameters
    ----------
    correct_per_class : dict
        Counts of correct predictions per class (TP).
    wrong_predictions : dict
        Dict mapping class to list of mispredicted classes (FN).
    predicted_as_class : dict
        Counts of predictions made as each class (TP + FP).
    num_classes : int
        Number of total classes.

    Returns
    -------
    dict : A dictionary with per-class precision, recall, and F1-score.
    """
    precision_dict = {}
    recall_dict = {}
    f1_dict = {}

    macro_f1_sum, weighted_f1_sum = 0, 0
    total_samples = sum(total_per_class.values())

    for i in range(num_classes):
        tp = correct_per_class.get(i, 0)
        fn = len(wrong_predictions.get(i, []))
        fp = predicted_as_class.get(i, 0) - tp
        support = total_per_class.get(i, 0)

        # Avoid division by zero
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0

        if (precision + recall) > 0:
            f1_score = 2 * precision * recall / (precision + recall)
        else:
            f1_score = 0

        precision_dict[i] = precision
        recall_dict[i] = recall
        f1_dict[i] = f1_score

        macro_f1_sum += f1_score
        weighted_f1_sum += f1_score * support

    macro_f1 = macro_f1_sum / num_classes
    weighted_f1 = weighted_f1_sum / total_samples if total_samples > 0 else 0

    macro_precision = precision_score(y_true=y_true, y_pred=y_pred, average='macro')
    macro_recall = recall_score(y_true=y_true, y_pred=y_pred, average='macro', zero_division=0.0)

    return {
        'per_class_precision': precision_dict,
        'per_class_recall': recall_dict,
        'per_class_f1': f1_dict,
        'macro_precision': macro_precision,
        'macro_recall': macro_recall,
        'macro_f1': macro_f1,
        'weighted_f1': weighted_f1
    }