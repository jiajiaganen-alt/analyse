# -*- coding: utf-8 -*-
"""Qwen2.5-0.5B-Instruct LoRA 指令微调脚本（CPU / GPU 均可运行）。

设计说明：
- 仅对 assistant 回复计算损失，system / user 部分的 label 置为 -100；
- LoRA 作用于 q/k/v/o/gate/up/down 七个投影层，可训练参数约占 1%；
- 默认使用本机已下载的 Qwen2.5-0.5B-Instruct，不依赖外网；
- 训练日志同时写入 CSV 与 console 日志，便于报告展示。

示例：
    python scripts/train_lora.py --max_steps 60 --max_length 640
    python scripts/train_lora.py --model_path /path/to/Qwen2.5-0.5B-Instruct --max_steps 120 --device cuda
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, get_cosine_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = Path(r"D:\ai_models\modelscope_cache\models\Qwen\Qwen2___5-0___5B-Instruct")


class InstructionDataset(Dataset):
    def __init__(self, path: Path, tokenizer, max_length: int) -> None:
        self.rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict:
        row = self.rows[index]
        messages = row["messages"]
        prompt_text = self.tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True
        )
        full_text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        prompt_ids = self.tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        full_ids = self.tokenizer(full_text, add_special_tokens=False)["input_ids"]
        if len(full_ids) > self.max_length:
            full_ids = full_ids[: self.max_length]
        prompt_len = min(len(prompt_ids), len(full_ids))
        labels = [-100] * prompt_len + full_ids[prompt_len:]
        return {
            "input_ids": torch.tensor(full_ids, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
            "attention_mask": torch.ones(len(full_ids), dtype=torch.long),
        }


def collate(batch: list[dict], pad_token_id: int) -> dict:
    max_len = max(len(item["input_ids"]) for item in batch)
    input_ids, labels, attention_mask = [], [], []
    for item in batch:
        pad_len = max_len - len(item["input_ids"])
        input_ids.append(torch.cat([item["input_ids"], torch.full((pad_len,), pad_token_id, dtype=torch.long)]))
        labels.append(torch.cat([item["labels"], torch.full((pad_len,), -100, dtype=torch.long)]))
        attention_mask.append(
            torch.cat([item["attention_mask"], torch.zeros(pad_len, dtype=torch.long)])
        )
    return {
        "input_ids": torch.stack(input_ids),
        "labels": torch.stack(labels),
        "attention_mask": torch.stack(attention_mask),
    }


def evaluate_loss(model, loader, max_batches: int = 6) -> float:
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for index, batch in enumerate(loader):
            if index >= max_batches:
                break
            batch = {key: value.to(model.device) for key, value in batch.items()}
            loss = model(**batch).loss
            losses.append(loss.item())
    model.train()
    return sum(losses) / max(len(losses), 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", default=str(DEFAULT_MODEL))
    parser.add_argument("--data_dir", default=str(ROOT / "data"))
    parser.add_argument("--output_dir", default=str(ROOT / "outputs"))
    parser.add_argument("--max_steps", type=int, default=60)
    parser.add_argument("--max_length", type=int, default=640)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight_decay", type=float, default=0.01)
    parser.add_argument("--warmup_steps", type=int, default=5)
    parser.add_argument("--eval_steps", type=int, default=20)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--dry_run", action="store_true", help="只跑 2 步，用于检查训练链路")
    args = parser.parse_args()

    if args.dry_run:
        args.max_steps = 2
        args.eval_steps = 1

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    device = "cuda" if (args.device in ("auto", "cuda") and torch.cuda.is_available()) else "cpu"
    use_bf16 = device == "cuda" and torch.cuda.is_bf16_supported()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "train_console.log"
    log_fh = log_path.open("w", encoding="utf-8")

    def log(message: str) -> None:
        print(message, flush=True)
        log_fh.write(message + "\n")
        log_fh.flush()

    started = time.time()
    log("=" * 78)
    log("知行学堂知识库问答模型 LoRA 微调")
    log(f"开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"模型：{args.model_path}")
    log(f"设备：{device} | bf16：{use_bf16} | 线程：{torch.get_num_threads()}")
    log(
        f"训练配置：steps={args.max_steps} max_length={args.max_length} "
        f"batch={args.batch_size} grad_accum={args.grad_accum} lr={args.lr}"
    )
    log("=" * 78)

    model_path = Path(args.model_path)
    if not (model_path / "config.json").exists():
        raise SystemExit(f"未找到模型：{model_path}，请先下载 Qwen2.5-0.5B-Instruct")
    if not (model_path / "model.safetensors").exists():
        raise SystemExit(f"模型权重不完整：{model_path / 'model.safetensors'}")

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    dtype = torch.bfloat16 if use_bf16 else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    model.config.use_cache = False

    from peft import LoraConfig, TaskType, get_peft_model

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.to(device)
    model.train()

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    log(f"可训练参数：{trainable:,} / {total:,}（{trainable / total:.2%}）")

    train_dataset = InstructionDataset(Path(args.data_dir) / "train.jsonl", tokenizer, args.max_length)
    val_dataset = InstructionDataset(Path(args.data_dir) / "validation.jsonl", tokenizer, args.max_length)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=lambda batch: collate(batch, tokenizer.pad_token_id),
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=lambda batch: collate(batch, tokenizer.pad_token_id),
    )

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr,
        weight_decay=args.weight_decay,
        betas=(0.9, 0.95),
    )
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=args.warmup_steps,
        num_training_steps=args.max_steps,
    )

    log_file = (output_dir / "training_log.csv").open("w", newline="", encoding="utf-8")
    writer = csv.writer(log_file)
    writer.writerow(["step", "loss", "val_loss", "lr", "grad_norm", "tokens", "elapsed_sec", "tokens_per_sec"])

    def infinite(loader):
        while True:
            for batch in loader:
                yield batch

    data_iter = infinite(train_loader)
    best_val = math.inf
    best_dir = output_dir / "lora_adapter_best"
    optimizer.zero_grad(set_to_none=True)
    running_loss = 0.0
    step_tokens = 0
    step_started = time.time()

    for step in range(1, args.max_steps + 1):
        micro_loss = 0.0
        for _ in range(args.grad_accum):
            batch = next(data_iter)
            batch = {key: value.to(device) for key, value in batch.items()}
            step_tokens += int(batch["attention_mask"].sum().item())
            outputs = model(**batch)
            loss = outputs.loss / args.grad_accum
            loss.backward()
            micro_loss += loss.item()
            running_loss += loss.item()

        grad_norm = torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], max_norm=1.0
        ).item()
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad(set_to_none=True)

        elapsed_total = time.time() - started
        step_elapsed = time.time() - step_started
        tokens_per_sec = step_tokens / max(step_elapsed, 1e-6)
        lr_now = scheduler.get_last_lr()[0]
        val_loss = ""

        if step % args.eval_steps == 0 or step == args.max_steps:
            val_loss = f"{evaluate_loss(model, val_loader):.4f}"
            if float(val_loss) < best_val:
                best_val = float(val_loss)
                if best_dir.exists():
                    shutil.rmtree(best_dir, ignore_errors=True)
                model.save_pretrained(str(best_dir))
                tokenizer.save_pretrained(str(best_dir))

        writer.writerow(
            [step, f"{micro_loss:.4f}", val_loss, f"{lr_now:.8f}", f"{grad_norm:.4f}", step_tokens,
             f"{elapsed_total:.1f}", f"{tokens_per_sec:.1f}"]
        )
        log_file.flush()

        log(
            f"[step {step:3d}/{args.max_steps}] loss={micro_loss:.4f} "
            f"val={val_loss or '-':>8} lr={lr_now:.2e} grad={grad_norm:.2f} "
            f"{step_tokens} tok {step_elapsed:.1f}s ({tokens_per_sec:.0f} tok/s)"
        )
        running_loss = 0.0
        step_tokens = 0
        step_started = time.time()

    log_file.close()
    adapter_dir = output_dir / "lora_adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    duration = time.time() - started
    summary = {
        "base_model": str(model_path),
        "base_model_name": "Qwen2.5-0.5B-Instruct",
        "device": device,
        "dtype": "bfloat16" if use_bf16 else "float32",
        "total_params": int(total),
        "trainable_params": int(trainable),
        "trainable_ratio": round(trainable / total, 6),
        "lora": {
            "r": args.lora_r,
            "alpha": args.lora_alpha,
            "dropout": args.lora_dropout,
            "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        },
        "train": {
            "max_steps": args.max_steps,
            "max_length": args.max_length,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "learning_rate": args.lr,
            "warmup_steps": args.warmup_steps,
            "samples": len(train_dataset),
            "validation_samples": len(val_dataset),
        },
        "best_val_loss": best_val if best_val != math.inf else None,
        "duration_seconds": round(duration, 1),
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "adapter_dir": str(adapter_dir),
        "best_adapter_dir": str(best_dir),
    }
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log("=" * 78)
    log(f"训练完成：{duration / 60:.1f} 分钟，最佳验证损失 {best_val:.4f}")
    log(f"LoRA 适配器：{adapter_dir}")
    log(f"训练摘要：{output_dir / 'training_summary.json'}")
    log_fh.close()


if __name__ == "__main__":
    main()
