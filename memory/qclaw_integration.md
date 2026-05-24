---
name: qclaw-integration
description: QClaw本地多模态Agent的API调用方式、图片压缩参数、评分流程
type: reference
originSessionId: 656cad54-9f29-4e3f-ab96-60f534650d89
---
## QClaw 是什么
本地运行的 AI agent，有多模态/视觉能力，充当 DeepSeek（纯文本）的"眼睛"。用来审查 ComfyUI 生成的图片质量。

## API 连接
- **地址**: `http://127.0.0.1:28789/v1/chat/completions`
- **认证**: Bearer token（具体 token 在 `test_qclaw_vision.py` 中）
- **格式**: OpenAI 兼容 API
- **多模态**: 支持 `image_url` 在 content 中（base64 或 URL）

## 图片压缩（必须！）
原始 ComfyUI 输出是 PNG（~2.9MB base64），直接发给 QClaw 会超长。必须在发送前压缩：
```python
from PIL import Image
img = Image.open(path).convert("RGB")
img.thumbnail((512, 512), Image.LANCZOS)  # 缩到 512px
img.save(temp_path, "JPEG", quality=65)    # JPEG 65% → ~15-27KB
```
压缩后 base64 约 15-27KB，可以正常发送。

## 评分流程
1. 压缩图片到 512px JPEG
2. base64 编码
3. 发送给 QClaw，prompt 中包含评分维度（民族元素辨识度、构图、色彩、光影、整体质感）
4. QClaw 返回中文评价 + 分数（/50）
5. 根据低分项调整 ComfyUI prompt 重新生成

## 关键文件
- `C:/Users/Administrator/temp_v5/test_qclaw_vision.py` — 首次测试 QClaw 多模态
- `C:/Users/Administrator/temp_v5/qclaw_review.py` — 批量审查 6 张图片
- QClaw 对油画风格的评分比写实风格更宽容

## Why
DeepSeek V4 Pro 是纯文本模型看不到图，QClaw 是本地的"眼睛"，用来替代用户手动看图判断。
