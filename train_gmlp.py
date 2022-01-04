from numpy.lib import utils
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from torch.utils.data import DataLoader

from model_gmlp import GMLPModel as Model
from utils import *

otu_path = './data/synthetic/otu0.csv'
adj_path = './data/synthetic/adj0.csv'
model_path = './models/gmlp_model.pth'

samples = './data/real/tuber/samples_tuber_little.csv'
interactions = './data/real/tuber/interactions_tuber_little.csv'
raw_samples = './data/real/raw_samples.csv'
raw_interactions = './data/real/raw_many_interactions.csv'
col = 40

batch_size = 256
epoch_num = 3000
contrasive_loss_m = 50
potential_loss_l = 0
potential_loss_k = 900
learning_rate = 1e-4
weight_decay = 5e-3
delta = 0.10

is_using_gpu = torch.cuda.is_available()
is_saving_model = True


class NContrastLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self,
                y_hat: torch.Tensor,
                y: torch.Tensor,
                tau: int = 1) -> torch.Tensor:
        y_hat = torch.exp(y_hat * tau)
        y_match_sum = torch.sum(y_hat * y, 1)
        y_sum = torch.sum(y_hat, 1)
        loss = -torch.log(y_match_sum * (y_sum)**(-1) + 1e-8).mean()
        return loss


class ContrastiveLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self,
                z_dist: torch.Tensor,
                y: torch.Tensor,
                m: int = contrasive_loss_m) -> torch.Tensor:
        zeros = torch.zeros(y.shape)
        if is_using_gpu:
            zeros = zeros.cuda()
        ls = z_dist**2
        ld = torch.maximum(zeros, m - z_dist)**2
        loss = y * ls + (1 - y) * ld
        return loss.mean() / 2


class PotentialLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self,
                z_dist: torch.Tensor,
                y: torch.Tensor,
                l: int = potential_loss_l,
                k: int = potential_loss_k) -> torch.Tensor:
        ls = (z_dist - l)**2
        ld = k * (z_dist + 1e-8)**(-1)
        loss = y * ls + (1 - y) * ld
        return loss.mean() / 2


# train model
def train_model(model, data_loader):
    # define criterion and optimizer
    criterion = NContrastLoss()
    # criterion = ContrastiveLoss()
    # criterion = PotentialLoss()
    # or use the
    optimizer = Adam(model.parameters(),
                     lr=learning_rate,
                     weight_decay=weight_decay)

    # train for epochs
    min_loss = float('inf')
    for epoch in range(epoch_num):
        # initialize loss and accuracy
        train_loss = 0.
        train_acc = 0.

        # train on batches
        for _, data in enumerate(data_loader):
            # get batch
            x, y = data
            # i, j = torch.triu_indices(y.shape[0], y.shape[1], 1)
            # y = y[i, j]
            if is_using_gpu:
                x, y = x.cuda(), y.cuda()
            # forward
            z, y_hat = model(x)
            # backward
            optimizer.zero_grad()
            loss = criterion(y_hat, y) + F.mse_loss(y_hat, y) * 100
            # loss = criterion(y_hat, y)
            loss.backward()
            optimizer.step()
            # accumulate loss and accuracy
            train_loss += loss
            train_acc += (abs(y - y_hat) < delta).float().mean()
            # true_y_hat = F.relu(1 - y_hat / contrasive_loss_m)
            # zeros = torch.zeros(y.shape)
            # if is_using_gpu:
            #     zeros = zeros.cuda()
            # true_y_hat = torch.maximum(zeros,
            #                            -(y_hat - potential_loss_l)**2 + 1)
            # train_acc += (abs(y - true_y_hat) < delta).float().mean()

        # get loss and accuracy of this epoch
        loader_step = len(data_loader)
        train_loss = train_loss / loader_step
        train_acc = train_acc / loader_step
        min_loss = min(min_loss, train_loss)
        # print training stats
        if epoch == 0 or (epoch + 1) % 10 == 0:
            print(
                f'--- Epoch: {epoch+1}, Loss: {train_loss:.6f}, Acc: {train_acc:.6f}'
            )

        # print some data for debug
        if (epoch + 1) == epoch_num:
            # print('z', z)
            print('y_hat', y_hat)
            # print('true_y_hat', true_y_hat)
            print('y', y)

    # save last model
    if is_saving_model:
        torch.save(model.state_dict(), model_path)


if __name__ == '__main__':
    # otu, adj = read_raw_data(otu_path, adj_path)
    # spieces_num = otu.shape[0]
    # sample_num = otu.shape[1]

    # train_dataset = get_emb_dateset()

    # data_loader = DataLoader(dataset=train_dataset,
    #                          batch_size=batch_size,
    #                          shuffle=False)
    # # clean_data(samples=samples,
    #            intereactions=interactions,
    #            raw_csv_samples=raw_samples,
    #            raw_csv_interactions=raw_interactions)
    train_data = get_real_dataset(samples=samples,
                                  interactions=interactions,
                                  col=col)
    # train_data = get_cora_dataset('train')
    # train_data = get_emb_dataset(col)
    data_loader = GMLPDataLoader(data=train_data,
                                 batch_size=batch_size,
                                 shuffle=True)

    model = Model(col, 256, 256)
    # model.load_state_dict(torch.load(model_path))
    if is_using_gpu:
        model = model.cuda()

    train_model(model, data_loader)
