
<h1 align="center">
  <p>WorldRWKV: Exploring RWKV7’s Understanding Capabilities of Any Modality in the World</p>
  
</h1>

\[ English | [中文](README_zh.md) \]
## Introduction
Implementing arbitrary modality input/output using native RWKV7 architecture; advancing toward building a World Model

## Release
- [3/7] 🔥 Release Repo **WorldRWKV: Exploring RWKV7’s Understanding Capabilities of Any Modality in the World**. Tech report and training details will be release next week at [HFModel](https://huggingface.co/WorldRWKV).

## Building Env
- Clone repo and direct to target DIR
```
git clone https://github.com/JL-er/WorldRWKV.git
cd WorldRWKV
```
- Dependencies
```
conda create -n world python=3.12
conda activate world
pip install -r requirements.txt #for Chinese User please add -i https://pypi.tuna.tsinghua.edu.cn/simple
# Recommend torch=>2.4.0
```
## Inference
> [!NOTE]
> Please make sure encoder model matchs encoder_type. More details are here:  world/world_encoder.py
```
from infer.worldmodel import Worldinfer
from PIL import Image


llm_path='/home/rwkv/model/rwkv7-3b-siglip/rwkv-0'
encoder_path='/home/rwkv/model/siglip2basep16s384'
encoder_type='siglip' #[clip, whisper, siglip, speech]

model = Worldinfer(model_path=llm_path, encoder_type=encoder_type, encoder_path=encoder_path)

img_path = './docs/03-Confusing-Pictures.jpg'
image = Image.open(img_path).convert('RGB')

text = '\x16User: What is unusual about this image?\x17Assistant:'

result = model.generate(text, image)

print(result)
```

## Training
> [!NOTE]
> Encoder model has to match encoder type while different tasks use different data types。You can register your own modality class in world/world_encoder.py
```
load_model=/home/rwkvos/model/rwkv/RWKV-x070-World-2.9B-v3-20250211-ctx4096.pth
proj_dir=/home/rwkvos/peter/out_model/rwkv7-3b-pretrain-siglip
data_file=/home/rwkvos/data/hf-imgs/pretrain595

n_layer=32
n_embd=2560

encoder_path="google/siglip2-base-patch16-384" #chose your own encoder model
encoder_type=siglip # Register encoder model in worldencoder
data_type=hf_img 

micro_bsz=32
epoch_save=1
epoch_steps=18605 
ctx_len=2048


HF_ENDPOINT="https://hf-mirror.com" python world_train.py \   # 中国用户使用"https://hf-mirror.com"下载模型
--load_model $load_model \
--proj_dir $proj_dir --data_file $data_file \
--data_type $data_type \
--vocab_size 65536 \
--n_layer $n_layer --n_embd $n_embd \
--ctx_len $ctx_len --micro_bsz $micro_bsz \
--epoch_steps $epoch_steps --epoch_count 1 --epoch_begin 0 --epoch_save $epoch_save \
--lr_init 1e-3 --lr_final 0 --warmup_steps 0 --beta1 0.9 --beta2 0.99 --adam_eps 1e-8 \
--accelerator gpu --devices 8 --precision bf16 --strategy deepspeed_stage_1 --grad_cp 1 \
--encoder_path $encoder_path --encoder_type $encoder_type \
--my_testing "x070" --train_step adapter rwkv #train_step 选择你要训练的部分，adapter、rwkv
```

## Web-demo (Using Gradio)
```
python audio_multiturns_web.py # For Audio QA and ASR
 
python visual_web.py  # For Visual QA 

```
## Abilities
### Tasks WorldRWKV already accomplished and future direction
| Already      | Future |
|:--------------:|:-----------:|
| asr            | ✅          |
| speech to text | ✅          |
| visual to text | ✅          |
| text to speech | ❌          |
| text to visual | ❌          |
|speech to speech| ❌          |


## Visual QA Benchmarks

| **Encoder** | **LLM** | **VQAV2** | **TextVQA** | **GQA** | **ScienceQA** | **Checkpoint** |
|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|
| [**Clip**](https://huggingface.co/openai/clip-vit-large-patch14-336)    | RWKV7-0.4B     | 62.04      | 31.72      | 49.32       |   51.10         |
|| RWKV7-1.5B     | 72.31       | 40.27       | 54.56       |   62.77          |
|             | RWKV7-3B       | 73.13       | 45.56       | 57.00       | 70.06       |
| [**SigLIP2**](https://huggingface.co/google/siglip2-base-patch16-384) | RWKV7-0.4B|    72.04     | 38.75       | 55.52       | 43.32       |[WorldRWKV/RWKV7-0.4B-siglip2](https://huggingface.co/WorldRWKV/RWKV7-0.4B-siglip2)     |
|             | RWKV7-1.5B   |     76.95    | 44.96       | 58.88       | 63.10       |[WorldRWKV/RWKV7-1.5B-siglip2](https://huggingface.co/WorldRWKV/RWKV7-1.5B-siglip2)     |
|             | RWKV7-3B      |     78.30     |   51.09          |   60.75          |     70.93        |[WorldRWKV/RWKV7-3B-siglip2](https://huggingface.co/WorldRWKV/RWKV7-3B-siglip2)       |

## ASR Benchmarks

| **Encoder** | **LLM** | **LibriSpeech** | **Aishell-1** |
|:--------------:|:--------------:|:--------------:|:--------------:|
|[**wavlm large**](https://huggingface.co/microsoft/wavlm-large) | RWKV7-0.4B | 2.43%(clean) | 9.68%(dev) |
|            |            | 6.51%(other) | 10.33%(test) |
|[**wavlm base+**](https://huggingface.co/microsoft/wavlm-base-plus) | RWKV7-0.4B | 3.08%(clean) | 12.40%(dev) |
|            |            | 10.38%(other) | 13.46%(test) |

## ASR & AUDIO QA (Demo)
| **Encoder** | **LLM** | **task** | **Checkpoint** |
|:--------------:|:--------------:|:--------------:|:--------------:|
|[**wavlm large**](https://huggingface.co/microsoft/wavlm-large) | RWKV7-0.1B | EN asr|[WorldRWKV/RWKV7-0.1B-wavlmLarge-ENASR-demo](https://huggingface.co/WorldRWKV/RWKV7-0.1B-wavlmLarge-ENASR-demo)|
|            |     RWKV7-0.4B       | EN asr|[WorldRWKV/RWKV7-0.4B-wavlmLarge-ENASR-demo](https://huggingface.co/WorldRWKV/RWKV7-0.4B-wavlmLarge-ENASR-demo)|
|            |     RWKV7-0.4B       | CN asr|[WorldRWKV/RWKV7-0.4B-wavlmLarge-CNASR-demo](https://huggingface.co/WorldRWKV/RWKV7-0.4B-wavlmLarge-CNASR-demo)|
|            |     RWKV7-0.4B       | EN qa|[WorldRWKV/RWKV7-0.4B-wavlmLarge-ENQA-demo](https://huggingface.co/WorldRWKV/RWKV7-0.4B-wavlmLarge-ENQA-demo)|


