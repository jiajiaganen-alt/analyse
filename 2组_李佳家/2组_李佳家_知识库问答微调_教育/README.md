# 知识库问答模型微调（Qwen2.5-0.5B-Instruct + LoRA）

> 课程作业 · 项目实战 —— 模型微调方向（对应文档 4.1 知识库项目模型微调）

## 1. 项目概述

本项目面向在线教育平台的**知识库检索增强问答**场景：检索服务召回若干制度条款后，模型需要

1. 严格依据召回资料作答，不编造政策、金额和期限；
2. 按行业术语和固定格式（结论 / 要点 / 依据 / 建议）输出；
3. 在答案中标注条款编号，使结论可追溯；
4. 当资料不足、无关或新旧版本冲突时明确拒答，并指出缺失信息。

项目完成了从**知识库语料构建 → 指令数据集生成 → LoRA 微调 → 自动评测 → 实验报告**的完整闭环，全部脚本离线可复现。

| 项目信息 | 说明 |
| --- | --- |
| 基座模型 | Qwen2.5-0.5B-Instruct（502.8M 参数） |
| 微调方式 | LoRA（r=16, alpha=32，7 个投影层，可训练参数 8.80M，占 1.75%） |
| 训练数据 | 420 条（5 个能力维度各 84 条） |
| 验证 / 测试 | 60 条 / 80 条 |
| 训练环境 | Windows 11 · Python 3.12 · PyTorch 2.12 · CPU（无 GPU） |
| 训练配置 | 60 步 · 序列长度 576 · batch 1 × 梯度累积 2 · lr 2.5e-4 |
| 评测样本 | 每能力维度 5 条，共 25 条留出测试样本 |

## 2. 目录结构

```
3组_张晨_知识库问答微调_教育/
├── README.md                     本文件
├── requirements.txt              依赖版本
├── data/
│   ├── knowledge/                6 篇知识库文档（markdown，可读版）
│   ├── knowledge_base.json       结构化语料（6 文档 / 37 条款）
│   ├── train.jsonl               训练集 420 条
│   ├── validation.jsonl          验证集 60 条
│   ├── test.jsonl                测试集 80 条
│   ├── dataset_stats.json        数据统计
│   └── preview_samples.json      报告用样例
├── scripts/
│   ├── kb_data.py                语料数据源（条款、要点、术语、流程）
│   ├── generate_dataset.py       数据集生成（5 个能力维度）
│   ├── check_dataset.py          数据质检
│   ├── train_lora.py             LoRA 微调（CPU/GPU）
│   ├── evaluate.py               模型评测（6 类指标）
│   └── make_report.py            生成离线 HTML 实验报告
├── outputs/
│   ├── lora_adapter/             最终 LoRA 适配器（第 60 步同时为验证损失最优，故只保留一份）
│   ├── training_log.csv          逐步训练日志
│   ├── train_console.log         训练控制台日志
│   ├── training_summary.json     训练摘要
│   ├── eval_base.json            基座模型评测结果
│   ├── eval_tuned.json           微调模型评测结果
│   └── eval_details.csv          评测明细
├── report/                       离线实验报告（index/dataset/training/evaluation/samples）
├── docs/                         数据说明、训练与评测说明、能力矩阵、测试记录、验收对照
└── 测试截图/                     真实浏览器截图（数据集、训练、评测、样例对比）
```

## 3. 快速开始

> 环境已预装 torch / transformers / peft，无需联网。若在新环境安装：`pip install -r requirements.txt`。

```bash
# 1. 生成数据集（固定随机种子，可重复）
python scripts/generate_dataset.py

# 2. 数据质检
python scripts/check_dataset.py

# 3. LoRA 微调（CPU 约 12-15 分钟；GPU 可调大 batch 与步数）
python scripts/train_lora.py --max_steps 60 --max_length 576 --grad_accum 2 --lr 2.5e-4

# 4. 评测基座模型与微调模型（各 25 条测试样本）
python scripts/evaluate.py --tag base --limit 5
python scripts/evaluate.py --tag tuned --adapter outputs/lora_adapter --limit 5

# 5. 生成实验报告（report/index.html）
python scripts/make_report.py
```

模型默认路径为 `D:\ai_models\modelscope_cache\models\Qwen\Qwen2___5-0___5B-Instruct`，可用 `--model_path` 指定其他本地 Qwen2.5 模型目录。

## 4. 数据集设计

知识库包含 6 篇制度文档、37 个条款（课程、退费、督学、直播、证书、发票），每个条款带摘要、要点、数字、术语与办理建议。围绕文档 4.1 的五项能力各生成 112 条样本：

| 能力维度 | 对应文档要求 | 训练重点 |
| --- | --- | --- |
| 行业术语与格式适配 | 4.1.1 | 制度解释 / 办理步骤两类回答格式，术语准确 |
| 检索内容忠实回答 | 4.1.2 | 带干扰片段时只使用目标条款数字，拒绝编造 |
| 多片段信息整合 | 4.1.3 | 两条相关条款合并作答，分别标注依据 |
| 证据引用与出处标注 | 4.1.4 | 原文摘录 + `[条款编号]`，引用与结论一致 |
| 资料不足时拒答 | 4.1.5 | 知识库外问题、新旧版本冲突两类拒答 |

数据构造细节与质检结果见 [`docs/数据说明.md`](docs/数据说明.md)。

## 5. 训练方法

- 使用 Qwen2.5 官方 chat template，将 system / user 部分的 label 置为 `-100`，只对 assistant 回复计算损失；
- LoRA 注入 `q_proj / k_proj / v_proj / o_proj / gate_proj / up_proj / down_proj` 七个投影层；
- AdamW + 余弦退火，warmup 5 步，梯度裁剪 1.0，验证集每 20 步评估一次并保存最优适配器；
- CPU 训练采用 fp32（无 bf16），开启 `torch.set_num_threads(6)`；
- 训练日志逐步记录 loss、验证 loss、学习率、梯度范数、吞吐，可复现实验曲线。

## 6. 评测方法

采用**规则化、可复算**的指标，避免主观打分：

| 指标 | 定义 |
| --- | --- |
| 引用 F1 | 引用编号是否真实存在于资料、是否覆盖标准依据条款 |
| 要点覆盖率 | 标准答案要点在生成答案中的字符 3-gram 覆盖比例（阈值 0.35） |
| 数字忠实度 | 生成答案中的数字能否在检索资料中找到（含时间、百分比） |
| 格式合规率 | 结论、要点、依据、分点等结构是否完整 |
| 术语准确率 | 条款中的行业术语在答案中的命中比例 |
| 拒答正确率 | 资料不足时是否拒答；可回答时是否避免误拒答 |

评测使用固定测试集（每维度 5 条），贪心解码，基线与微调使用完全相同的提示词与生成参数。

## 7. 实验结果

完整指标与逐条样例见 [`report/index.html`](report/index.html)（可直接用浏览器打开），以及 `outputs/eval_base.json`、`outputs/eval_tuned.json`。

| 指标 | 基线模型 | 微调模型 | 变化 |
| --- | --- | --- | --- |
| 引用 F1 | 0.100 | **0.950** | +0.850 |
| 要点覆盖率 | 0.774 | 0.888 | +0.114 |
| 数字忠实度 | 0.980 | **1.000** | +0.020 |
| 格式合规率 | 0.040 | **0.880** | +0.840 |
| 术语准确率 | 0.825 | 0.808 | -0.017 |
| 拒答正确率 | 0.880 | 0.920 | +0.040 |
| **综合得分（25 条）** | **0.527** | **0.859** | **+0.332** |

分维度综合得分（基线 → 微调）：

- 行业术语与格式适配：0.633 → **0.968**
- 检索内容忠实回答：0.474 → **0.980**
- 多片段信息整合：0.445 → **0.805**
- 证据引用与出处标注：0.601 → **0.941**
- 资料不足拒答：0.480 → **0.600**

> 拒答维度得分偏低的原因是测试集包含 2 条“新旧版本冲突”样本，模型误用了历史版本数字；3 条“资料不足”样本全部正确拒答。详细分析见 `docs/训练与评测说明.md` 第 5.3 节。

- 评测对比图：`测试截图/04_评测指标对比.png`
- 引用 / 拒答 / 多片段真实输出对比：`测试截图/05_样例对比_基线与微调.png`
- 训练损失曲线：`测试截图/03_训练过程与损失曲线.png`

> 本次实验在无 GPU 的 CPU 环境完成，训练步数有限（60 步），因此提升集中在“格式、引用与拒答行为”；多片段整合和术语压缩仍是短板，在 GPU 上增加步数与数据规模可进一步拉开差距（见第 9 节）。

## 8. 产物说明

| 文件 | 说明 |
| --- | --- |
| `outputs/lora_adapter/adapter_model.safetensors` | LoRA 权重（约 35 MB），可直接配合基座模型加载 |
| `outputs/training_log.csv` | 每步 loss / lr / grad_norm / 吞吐 |
| `outputs/eval_base.json` / `eval_tuned.json` | 逐条生成结果与指标 |
| `report/*.html` | 离线实验报告，含损失曲线、指标对比、样例对比 |
| `测试截图/*.png` | 1440px 真实浏览器截图 |

加载适配器示例：

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base = "D:/ai_models/modelscope_cache/models/Qwen/Qwen2___5-0___5B-Instruct"
model = AutoModelForCausalLM.from_pretrained(base, torch_dtype="auto", device_map="cpu")
model = PeftModel.from_pretrained(model, "outputs/lora_adapter")
tokenizer = AutoTokenizer.from_pretrained("outputs/lora_adapter")
```

## 9. 局限与改进方向

1. **训练规模有限**：CPU 环境只完成 60 步（约 12 分钟），数据曝光不足，部分指标提升有限；在 GPU 上建议 3-5 个 epoch、序列长度 1024、batch 8。
2. **基座模型较小**：0.5B 模型的长上下文整合与抗干扰能力有限，可将同一份数据用于 Qwen2.5-7B-Instruct 的 LoRA 训练。
3. **评测以规则指标为主**：覆盖引用、数字、格式与拒答，但语义流畅度和答案完整性仍建议加入人工抽检或 LLM-as-judge。
4. **数据为模板生成**：表达多样性有限，后续可引入真实客服会话做指令扩充与难例挖掘。

## 10. 交付清单

- 代码：`scripts/` 下 6 个脚本，无第三方未声明依赖；
- 数据：560 条指令样本 + 6 篇知识文档 + 统计文件；
- 模型：LoRA 适配器与训练日志；
- 文档：README、数据说明、训练与评测说明、能力覆盖矩阵、测试记录、验收对照；
- 截图：5 张（数据集、训练、评测、样例对比、总览）。
