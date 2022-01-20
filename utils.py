import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import torch
from scipy.sparse import coo_matrix
from torch.utils.data import DataLoader, TensorDataset
from torch_geometric.data import Data
from torch_geometric.datasets import Planetoid
from torch_sparse import tensor


class GMLPDataLoader():
    def __init__(self,
                 data: Data,
                 batch_size: int,
                 shuffle: bool = False,
                 drop_last: bool = False):
        self.x = data.x.type(torch.float32)
        self.y = torch.sparse_coo_tensor(data.edge_index,
                                         torch.ones(data.edge_index.shape[1]),
                                         (data.x.shape[0], data.x.shape[0]))
        self.y = self.y.to_dense()
        self.y = torch.logical_or(self.y, self.y.T).type(torch.float32)
        self.y = self.y.fill_diagonal_(1.)
        self.batch_size = batch_size
        self.shuffle = shuffle
        if drop_last:
            self.sample_num = len(self.x) // self.batch_size
        else:
            self.sample_num = (len(self.x) + self.batch_size -
                               1) // self.batch_size

    def __iter__(self):
        for _ in range(self.sample_num):
            random_index = torch.randperm(len(self.x))[:self.batch_size]
            x_batch = self.x[random_index]
            y_batch = self.y[random_index, :][:, random_index]
            yield x_batch, y_batch

    def __len__(self):
        return self.sample_num


# data cleaning
def clean_data(in_smpl_path: str, in_intr_path: str, out_smpl_path: str,
               out_intr_path: str) -> None:
    """Clean data.

    Args:
        in_smpl_path (str): Path of input samples file.
        in_intr_path (str): Path of input interactions file.
        out_smpl_path (str): Path of output samples file.
        out_intr_path (str): Path of output interactions file.
    """
    # read raw data
    samples_df = pd.read_csv(in_smpl_path)
    interactions_df = pd.read_csv(in_intr_path, usecols=[0, 1])

    # keep only the rows with at least n non-zero values
    samples_df = samples_df.replace(0, np.nan)
    samples_df = samples_df.dropna(thresh=7)
    samples_df = samples_df.replace(np.nan, 0)

    # get intersection of genes
    gene_in_samples = samples_df.iloc[:, 0].to_numpy()
    gene_in_interactions = interactions_df.to_numpy()
    cleaned_genes = np.intersect1d(gene_in_samples, gene_in_interactions)

    # get cleaned samples
    raw_samples = samples_df.to_numpy()
    new_samples = samples_df.columns.to_numpy()

    for x in raw_samples:
        if x[0] in cleaned_genes:
            new_samples = np.vstack((new_samples, x))

    pd.DataFrame(new_samples).to_csv(out_smpl_path, header=False, index=False)

    # get cleaned interactions
    raw_interactions = interactions_df.to_numpy()
    new_interactions = interactions_df.columns.to_numpy()

    for x in raw_interactions:
        if x[0] in cleaned_genes and x[1] in cleaned_genes:
            new_interactions = np.vstack((new_interactions, x))

    pd.DataFrame(new_interactions).to_csv(out_intr_path,
                                          header=False,
                                          index=False)

    # TODO: the following codes are quick and dirty, need to be improved
    # get the largest connected component
    data = get_dataset(out_smpl_path, out_intr_path)

    y = torch.sparse_coo_tensor(data.edge_index,
                                torch.ones(data.edge_index.shape[1]),
                                (data.x.shape[0], data.x.shape[0]))
    y = y.to_dense().type(torch.float32).numpy()

    G = nx.convert_matrix.from_numpy_matrix(y)
    c = max(nx.connected_components(G), key=len)

    cleaned_genes = cleaned_genes[list(c)]

    # get cleaned samples
    raw_samples = samples_df.to_numpy()
    new_samples = samples_df.columns.to_numpy()

    for x in raw_samples:
        if x[0] in cleaned_genes:
            new_samples = np.vstack((new_samples, x))

    pd.DataFrame(new_samples).to_csv(out_smpl_path, header=False, index=False)

    # get cleaned interactions
    raw_interactions = interactions_df.to_numpy()
    new_interactions = interactions_df.columns.to_numpy()

    for x in raw_interactions:
        if x[0] in cleaned_genes and x[1] in cleaned_genes:
            new_interactions = np.vstack((new_interactions, x))

    pd.DataFrame(new_interactions).to_csv(out_intr_path,
                                          header=False,
                                          index=False)


def get_dataset(smpl_path: str, intr_path: str, col: int = 0) -> Data:
    """Generate dataset from csv files.

    Args:
        smpl_path (str): Path of samples file.
        intr_path (str): Path of interactions file.
        col (int, optional): Only keep the first col columns. 0 means to keep all columns. Defaults to 0.

    Returns:
        Data: Data.
    """
    samples_df = pd.read_csv(smpl_path)
    interactions_df = pd.read_csv(intr_path)

    if col:
        x = samples_df.iloc[:, 1:col + 1].to_numpy(dtype=np.float32)
    else:
        x = samples_df.iloc[:, 1:].to_numpy(dtype=np.float32)
    x = torch.as_tensor(x, dtype=torch.float32)

    gene_names = samples_df.iloc[:, 0].to_list()
    gene1 = interactions_df.iloc[:, 0].to_list()
    gene2 = interactions_df.iloc[:, 1].to_list()

    gene1_index = torch.as_tensor([gene_names.index(i) for i in gene1],
                                  dtype=torch.int32)
    gene2_index = torch.as_tensor([gene_names.index(i) for i in gene2],
                                  dtype=torch.int32)

    edge_index = torch.vstack((gene1_index, gene2_index))

    print('get dataset done')
    print('x.shape', x.shape)
    print('edge_index.shape', edge_index.shape)
    return Data(x=x, edge_index=edge_index)


# get dataset
def get_cora_dataset(train: bool, col: int = 0) -> Data:
    dataset = Planetoid('./data', 'Cora')
    data = dataset[0]
    if train:
        mask = data.train_mask
    else:
        mask = data.test_mask
    # 获得非零元素的索引
    mask = np.array(mask).astype(float)
    mask_index = np.flatnonzero(mask)
    # 由 edge_index 生成邻接矩阵
    y = torch.sparse_coo_tensor(data.edge_index,
                                torch.ones(data.edge_index.shape[1]),
                                (data.x.shape[0], data.x.shape[0]))
    y = y.to_dense()
    # 筛选特定的行和列
    y = y[np.ix_(mask_index, mask_index)]
    x = data.x[np.ix_(mask_index)]
    # 压缩x的特征
    print(x.shape)
    if (col != 0):
        x = x[:, :col]

    # 转化为edge_index
    y_sparse = coo_matrix(y)
    y_indices = np.vstack((y_sparse.row, y_sparse.col))
    edge_index = torch.LongTensor(y_indices)
    return Data(x=x, edge_index=edge_index)


def lsa_pair(List1, List2, N):
    O1 = List1
    O2 = List2
    psm = np.zeros([N + 1, N + 1])
    nsm = np.zeros([N + 1, N + 1])
    i = 0
    j = 0
    max_s = -1000
    max_p = [0, 0]
    flag = 0
    for i in range(1, N + 1):
        for j in range(max(1, i - 3), min(N, i + 3) + 1):
            s1 = O1[i - 1] * O2[j - 1]
            psm[i][j] = max(0., psm[i - 1][j - 1] + s1)
            nsm[i][j] = max(0, nsm[i - 1][j - 1] - s1)
            if psm[i][j] > max_s:
                max_s = psm[i][j]
                max_p[0] = i
                max_p[1] = j
                flag = 1
            if nsm[i][j] > max_s:
                max_s = nsm[i][j]
                max_p[0] = i
                max_p[1] = j
                flag = -1
    if flag == 1:
        return max_s / N
    else:
        return -1 * max_s / N


def lsa(data, D):
    N = len(data)
    lss = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            lss[i][j] = lss_pair(data[i], data[j], len(data[i]))
    return lss


# draw graph
def draw_graph(G, pos, node_size, node_color):
    nx.draw_networkx_nodes(
        G,
        pos,
        alpha=0.9,
        node_size=node_size,
        node_color=node_color,
        cmap=plt.cm.Wistia,
        edgecolors='tab:gray',
    )
    nx.draw_networkx_edges(
        G,
        pos,
        arrowstyle='-',
        alpha=0.5,
    )
    nx.draw_networkx_edges(
        G,
        pos,
        arrowstyle='-',
        alpha=0.5,
        width=7,
        edge_color='tab:blue',
    )
    nx.draw_networkx_labels(
        G,
        pos,
        alpha=0.8,
        # font_color='whitesmoke'
    )

    plt.axis('off')
    plt.show()


# draw raw graph
def draw_raw_graph(G, pos, node_size, node_color):
    nx.draw_networkx_nodes(
        G,
        pos,
        alpha=0.9,
        node_size=node_size,
        cmap=plt.cm.Wistia,
        edgecolors='tab:gray',
    )
    nx.draw_networkx_edges(
        G,
        pos,
        arrowstyle='-',
        alpha=0.5,
    )
    nx.draw_networkx_edges(
        G,
        pos,
        arrowstyle='-',
        alpha=0.5,
        width=7,
        edge_color='tab:blue',
    )
    nx.draw_networkx_labels(
        G,
        pos,
        alpha=0.8,
        # font_color='whitesmoke'
    )

    plt.axis('off')
    plt.show()
