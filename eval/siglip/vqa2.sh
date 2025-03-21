answer_file=/home/rwkvos/data/eval/vqav2/answers/rwkv7-3b-siglip
mod="google/siglip2-base-patch16-384"
type=siglip
python -m eval.vqa2 \
    --model-path /home/rwkvos/JL/out_model/rwkv7-3b-siglip/rwkv-0 \
    --question-file /home/rwkvos/data/eval/vqav2/llava_vqav2_mscoco_test-dev2015.jsonl \
    --image-folder /home/rwkvos/data/eval/vqav2/test2015 \
    --answers-file $answer_file/merge.jsonl \
    --conv_mode $mod \
    --type $type \
    --temperature 0

python -m eval.eval_vqav2 \
    --dir /home/rwkvos/data/eval/vqav2 \
    --split llava_vqav2_mscoco_test-dev2015 \
    --ckpt $answer_file