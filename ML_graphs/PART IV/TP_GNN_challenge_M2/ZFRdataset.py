

import torch

from torch_geometric.data import (InMemoryDataset)




class ZFR(InMemoryDataset):

    def __init__(self, root,dataset = 'train', transform=None, pre_transform=None,
                 pre_filter=None):
        super(ZFR, self).__init__(root, transform, pre_transform, pre_filter)
        if dataset == 'train':
            self.data, self.slices = torch.load(self.processed_paths[0])
        if dataset == 'test':
            self.data, self.slices = torch.load(self.processed_paths[1])

        

    

    

    @property
    def processed_file_names(self):
        return ['data_train.pt','data_test.pt']



   