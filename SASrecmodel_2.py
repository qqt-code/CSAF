from torch import nn as nn
from attention import *
import math


class SASRec_2(nn.Module):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.embedding = SASEmbedding(self.args)
        self.model = SASModel(self.args)
        self.truncated_normal_init()

    def truncated_normal_init(self, mean=0, std=0.02, lower=-0.04, upper=0.04):
        with torch.no_grad():
            l = (1. + math.erf(((lower - mean) / std) / math.sqrt(2.))) / 2.
            u = (1. + math.erf(((upper - mean) / std) / math.sqrt(2.))) / 2.

            for n, p in self.model.named_parameters():
                if not 'layer_norm' in n:
                    p.uniform_(2 * l - 1, 2 * u - 1)
                    p.erfinv_()
                    p.mul_(std * math.sqrt(2.))
                    p.add_(mean)
        
    def forward(self, x):
        x, mask = self.embedding(x) # seq (64,200)
        scores = self.model(x, self.embedding.token.weight, mask)
        return scores


class SASEmbedding(nn.Module):
    def __init__(self, args):
        super().__init__()
        vocab_size = args.num_items + 2
        hidden = args.bert_hidden_units
        max_len = args.bert_max_len
        dropout = args.bert_dropout

        self.token = TokenEmbedding(
            vocab_size=vocab_size, embed_size=hidden)
        self.position = PositionalEmbedding(
            max_len=max_len, d_model=hidden)

        self.dropout = nn.Dropout(p=dropout)

    def get_mask(self, x):
        if len(x.shape) > 2:
            return (x[:, :, 1:].sum(-1) > 0).unsqueeze(1).repeat(1, x.size(1), 1).unsqueeze(1)
        return (x > 0).unsqueeze(1).repeat(1, x.size(1), 1).unsqueeze(1)

    def forward(self, x):
        mask = self.get_mask(x) # 掩码mask (64,200)
        if len(x.shape) > 2:
            pos = self.position(x[:, :, 1:].sum(-1))
            x = torch.matmul(x, self.token.weight) + pos
        else: #进这一步 # self.token即为item_emb,self.position即为pos_emb
            #print(self.token(x))
            #print(self.position(x))
            x = self.token(x) + self.position(x) # origin x:(64,200);transform x:(64,200,64)
        return self.dropout(x), mask


class SASModel(nn.Module):
    def __init__(self, args):
        super().__init__()
        hidden = args.bert_hidden_units
        heads = args.bert_num_heads
        head_size = args.bert_head_size
        dropout = args.bert_dropout
        attn_dropout = args.bert_attn_dropout
        layers = args.bert_num_blocks

        self.transformer_blocks = nn.ModuleList([SASTransformerBlock(
            hidden, heads, head_size, hidden * 4, dropout, attn_dropout) for _ in range(layers)])

    def forward(self, x, embedding_weight, mask):#embedding_weight.shape = (3417,64)
        for transformer in self.transformer_blocks:
            x = transformer.forward(x, mask)
        scores = torch.matmul(x, embedding_weight.permute(1, 0)) #x.shape = (64,200,64) embedding_weight.shape = (64,3417)
        return scores