########################################################################################################
# The RWKV Language Model - https://github.com/BlinkDL/RWKV-LM
########################################################################################################
from torch.utils.checkpoint import checkpoint as torch_checkpoint
from torch.profiler import profile, record_function, ProfilerActivity
#from adam_mini import Adam_mini

import os, math, gc, importlib
import torch

import torch.nn as nn
from torch.nn import functional as F
import lightning as pl
from lightning.pytorch.strategies import DeepSpeedStrategy
if importlib.util.find_spec('deepspeed'):
    import deepspeed
    from deepspeed.ops.adam import DeepSpeedCPUAdam, FusedAdam
    
from .block import Block
from .loss import L2Wrap

class RWKV(pl.LightningModule):
    def __init__(self, args, modality=None):
        super().__init__()
        self.args = args
        if not hasattr(args, 'dim_att'):
            args.dim_att = args.n_embd
        if not hasattr(args, 'dim_ffn'):
            args.dim_ffn = args.n_embd * 4

        assert args.n_embd % 32 == 0
        assert args.dim_att % 32 == 0
        assert args.dim_ffn % 32 == 0

        self.adapter = nn.Sequential(
            nn.Linear(1024 * 5, 2048),
            nn.ReLU(),
            nn.Linear(2048, args.n_embd),
        )

        self.emb = nn.Embedding(args.vocab_size, args.n_embd)

        self.blocks = nn.ModuleList([Block(args, i) for i in range(args.n_layer)])

        self.ln_out = nn.LayerNorm(args.n_embd)
        self.head = nn.Linear(args.n_embd, args.vocab_size, bias=False)

        #self.modality = modality


    def pad_mod(self, tensor_list, modality_list):
        """
        对一个包含不同长度张量的列表进行填充，使所有张量的长度相同且为16的整数倍，并生成掩码。
        参数:
            tensor_list (list of torch.Tensor): 输入的张量列表，每个张量形状为 [seq_len]。
            pad_value (int, optional): 填充值，默认值为 0。
        返回:
            padded_tensor (torch.Tensor): 填充后的张量，形状为 [batch_size, target_len]。
            mask (torch.Tensor): 填充掩码，1 表示有效数据，0 表示填充部分。
        """
        # 找到列表中最大长度
        # for token, signal in zip(tensor_list, modality_list):
        #     max_len = token.size(0) + signal.size(0)
        max_len = max((token.size(0) + signal.size(1)) for token, signal in zip(tensor_list, modality_list))
        # 计算目标长度（向上取整到16的整数倍）
        target_len = ((max_len + 15) // 16 * 16)+1

        masks = torch.zeros((len(tensor_list), target_len-1), dtype=torch.int32)
        x = []
        y = []
        for token, signal, mask in zip(tensor_list, modality_list, masks):
            pad_len = target_len-(token.size(0) + signal.size(1))
            padded_token = F.pad(token, (0, pad_len), value=0)
            x_token = padded_token[:-1]
            y_token = F.pad(padded_token, (signal.size(1)-1, 0), value=0)

            mask[signal.size(1) : -pad_len] = 1 
            
            x.append(x_token)
            y.append(y_token)

        y = torch.stack(y, dim=0)


       
        return modality_list, x, y, masks.cuda()


    def forward(self, idx, signs= None):
        args = self.args
        #B, T = idx.size()
        # assert T <= args.ctx_len, "Cannot forward, model ctx_len is exhausted."

        x_list = []
        if signs!=None:
            for token, sign in zip(idx, signs):
                sign_emb = self.adapter(sign)
                x_emb = self.emb(token)
            # #print(sign_emb.shape, x.shape)
                x_list.append(torch.cat([sign_emb.squeeze(0),x_emb], dim=0))
            x = torch.stack(x_list, dim=0)
        else:
            x = self.emb(idx)

        v_first = torch.empty_like(x)
        for block in self.blocks:
            if args.grad_cp == 1:
                if args.state_tune or args.train_type == 'state' or args.peft !='none':
                    x, v_first = torch_checkpoint(block, x, v_first ,use_reentrant=False)
                else:
                    x, v_first = deepspeed.checkpointing.checkpoint(block, x, v_first)
            else:
                x, v_first = block(x, v_first)

        x = self.ln_out(x)
        x = self.head(x)

        return x

    def training_step(self, batch, batch_idx):
        args = self.args

        #sign, idx, targets, mask = batch
        signs, tokens = batch
        #sign, idx, targets, mask = self.merge_modality(signs, tokens)
        sign, idx, targets, mask = self.pad_mod(tokens, signs)

        mask = mask.view(-1)
        sum_mask = torch.sum(mask).item()
        logits = self(idx,sign)
        #max_indices = torch.argmax(logits, dim=-1)

        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1), reduction='none')
        loss = torch.sum(loss * mask) / sum_mask
    

        return L2Wrap.apply(loss, logits)


    def configure_optimizers(self):
        args = self.args
        
        lr_decay = set()
        lr_1x = set()
        lr_2x = set()
        lr_3x = set()
        for n, p in self.named_parameters():
            if not p.requires_grad:
                continue
            if (("_w1" in n) or ("_w2" in n)) and (args.layerwise_lr > 0):
                lr_1x.add(n)
            elif (("time_mix" in n) or ("time_maa" in n)) and (args.layerwise_lr > 0):
                if args.my_pile_stage == 2:
                    lr_2x.add(n)
                else:
                    lr_1x.add(n)
            elif (("time_decay" in n) or ("time_daaaa" in n)) and (args.layerwise_lr > 0):
                if args.my_pile_stage == 2:
                    lr_3x.add(n)
                else:
                    lr_2x.add(n)
            elif ("time_faaaa" in n) and (args.layerwise_lr > 0):
                if args.my_pile_stage == 2:
                    lr_2x.add(n)
                else:
                    lr_1x.add(n)
            elif ("time_first" in n) and (args.layerwise_lr > 0):
                lr_3x.add(n)
            elif (len(p.squeeze().shape) >= 2) and (args.weight_decay > 0):
                lr_decay.add(n)
            else:
                lr_1x.add(n)

        lr_decay = sorted(list(lr_decay))
        lr_1x = sorted(list(lr_1x))
        lr_2x = sorted(list(lr_2x))
        lr_3x = sorted(list(lr_3x))

        param_dict = {n: p for n, p in self.named_parameters()}
        
        if args.layerwise_lr > 0:
            if args.my_pile_stage == 2:
                optim_groups = [
                    {"params": [param_dict[n] for n in lr_1x], "weight_decay": 0.0, "my_lr_scale": 1.0},
                    {"params": [param_dict[n] for n in lr_2x], "weight_decay": 0.0, "my_lr_scale": 5.0},# test: 2e-3 / args.lr_init},
                    {"params": [param_dict[n] for n in lr_3x], "weight_decay": 0.0, "my_lr_scale": 5.0},# test: 3e-3 / args.lr_init},
                ]
            else:
                optim_groups = [
                    {"params": [param_dict[n] for n in lr_1x], "weight_decay": 0.0, "my_lr_scale": 1.0},
                    {"params": [param_dict[n] for n in lr_2x], "weight_decay": 0.0, "my_lr_scale": 2.0},
                    {"params": [param_dict[n] for n in lr_3x], "weight_decay": 0.0, "my_lr_scale": 3.0},
                ]
        else:
            optim_groups = [{"params": [param_dict[n] for n in lr_1x], "weight_decay": 0.0, "my_lr_scale": 1.0}]

        if args.weight_decay > 0:
            optim_groups += [{"params": [param_dict[n] for n in lr_decay], "weight_decay": args.weight_decay, "my_lr_scale": 1.0}]
            
            if self.deepspeed_offload:
                return DeepSpeedCPUAdam(optim_groups, lr=self.args.lr_init, betas=self.args.betas, eps=self.args.adam_eps, bias_correction=True, adamw_mode=True, amsgrad=False)
            return FusedAdam(optim_groups, lr=self.args.lr_init, betas=self.args.betas, eps=self.args.adam_eps, bias_correction=True, adam_w_mode=True, amsgrad=False)
        else:
            
            if self.deepspeed_offload:
                return DeepSpeedCPUAdam(optim_groups, lr=self.args.lr_init, betas=self.args.betas, eps=self.args.adam_eps, bias_correction=True, adamw_mode=False, weight_decay=0, amsgrad=False)
            return FusedAdam(optim_groups, lr=self.args.lr_init, betas=self.args.betas, eps=self.args.adam_eps, bias_correction=True, adam_w_mode=False, weight_decay=0, amsgrad=False)
        # return ZeroOneAdam(optim_groups, lr=self.args.lr_init, betas=self.args.betas, eps=self.args.adam_eps, bias_correction=True, weight_decay=0, amsgrad=False, cuda_aware=False)

    @property
    def deepspeed_offload(self) -> bool:
        strategy = self.trainer.strategy
        if isinstance(strategy, DeepSpeedStrategy):
            cfg = strategy.config["zero_optimization"]
            return cfg.get("offload_optimizer") or cfg.get("offload_param")
        return False

    def generate_init_weight(self):
        print(
            f"""
############################################################################
#
# Init model weight (slow for large models)...
#
############################################################################
"""
        )
        m = {}
        for n in self.state_dict():
            p = self.state_dict()[n]
            shape = p.shape

            gain = 1.0
            scale = 1.0
            if "ln_" in n or ".ln" in n or "time_" in n or "_mask" in n or "pos_emb" in n or '.mask.' in n:
                if 'ln_x.weight' in n:
                    layer_scale = (1+int(n.split('.')[1])) / self.args.n_layer
                    m[n] = (p * 0.0) + (layer_scale ** 0.7)
                else:
                    m[n] = p
            else:
                if n == "emb.weight":
                    scale = -1 * self.args.lr_init
                else:
                    if shape[0] > shape[1]:
                        gain = math.sqrt(shape[0] / shape[1])

                    zero = [".att.output.", ".ffn.value.", ".ffn.receptance.", ".ffnPre.value.", ".ffnPre.receptance.", "head_q.", '.oo.', '.rr.']

                    for kk in zero:
                        if kk in n:
                            scale = 0
                    if n == "head.weight":
                        scale = 0.5
                    if "head_k." in n:
                        scale = 0.1
                    if "head_q." in n:
                        scale = 0

                print(f"{str(shape[0]).ljust(5)} {str(shape[1]).ljust(5)} {str(scale).ljust(4)} {n}")

                if self.args.accelerator.upper() == "GPU":
                    m[n] = torch.empty((shape[0], shape[1]), device="cuda")
                else:
                    m[n] = torch.empty((shape[0], shape[1]))

                if scale == 0:
                    nn.init.zeros_(m[n])
                elif scale < 0:
                    nn.init.uniform_(m[n], a=scale, b=-scale)
                else:
                    nn.init.orthogonal_(m[n], gain=gain * scale)

            m[n] = m[n].cpu()
            if os.environ["RWKV_FLOAT_MODE"] == "fp16":
                m[n] = m[n].half()
            elif os.environ["RWKV_FLOAT_MODE"] == "bf16":
                m[n] = m[n].bfloat16()

            # if n == "emb.weight":
            #     print(m[n])

        gc.collect()
        torch.cuda.empty_cache()
        return m
