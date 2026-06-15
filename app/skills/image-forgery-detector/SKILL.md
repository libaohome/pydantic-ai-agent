---
name: image-forgery-detector
description: 使用启发式分析（元数据、压缩伪影、纹理一致性、LBP、梯度相干性、ELA）检测伪造、篡改或AI生成的图像。当用户提供图片路径或URL并要求检查图片是否伪造/篡改/修图/假图/AI生成或进行图像取证时使用。
---

# 图像伪造检测器

通过多维启发式分析检测图片是否被伪造、篡改或AI生成。

## When to Use

当用户提供图片路径或 URL，并要求检查是否伪造、篡改、修图、假图、AI 生成或进行图像取证时使用。

## Scripts（必须用 run_skill_script，不要用 read_skill_resource）

1. 先调用 `load_skill("image-forgery-detector")`
2. 再调用 `run_skill_script`：

- **`scripts/detect.py`** — 检测图片
  - `image`（required）：本地路径或图片 URL

Example:

```text
run_skill_script(
  skill_name="image-forgery-detector",
  script_name="scripts/detect.py",
  args={"image": "https://example.com/photo.png"}
)
```

## 使用方法（命令行参考）

## 检测流水线

### 1. 元数据检测
解析JPEG段（EXIF、JFIF、Adobe标记）和PNG文本块（tEXt、iTXt、eXIf）。标记以下内容：
- 已知编辑软件关键词（Photoshop、GIMP、美图等）
- AIGC/内容溯源签名（Label=1、ContentProducer、doubao等）

### 2. JPEG压缩分析
- 量化表与标准亮度表匹配，估算质量
- 8x8块边界分析（"块效应"），检测二次压缩伪影

### 3. 全局视觉特征
- 亮度均值/标准差、饱和度、调色板密度、直方图峰值
- 检测：异常亮度、过饱和、纹理匮乏区域

### 4. 局部特征分布
- 基于Sobel的角点类特征检测（4×4网格）
- 标记：特征密度低、过度集中、分布不均

### 5. 截图特征检测
- 宽高比与常见屏幕分辨率对比
- 边缘密度、文本行比例、纯色区域比例
- 识别：截图、屏幕录制、微信转发图片

### 6. 文档/纸质件篡改检测
- 纸张区域分割（亮度>=0.58，饱和度<=0.28）
- 逐块标准差→纹理一致性分析
- 可疑块比例、聚类指标（泛洪填充连通分量）
- 文本行波动分析
- LBP（局部二值模式）相邻块间纹理不一致性
- 梯度方向不一致性分析
- 通过拉普拉斯方差检测噪声不一致性
- 通过JPEG重新编码进行ELA（错误级别分析）

### 7. 决策引擎
将证据信号分为三个类别：

| 状态 | 描述 |
|------|------|
| `有伪造` | 检测到强篡改信号 |
| `待确认` | 可疑但未达强阈值 |
| `截图` | 干净的截图，无篡改 |
| `无伪造` | 未发现显著异常 |

## 输出字段

| 字段 | 描述 |
|------|------|
| `review_status` | 最终判定（有伪造/待确认/截图/无伪造） |
| `forgery_score` | 整体伪造风险（0-100） |
| `tamper_index` | 复合篡改指数（0-100） |
| `tamper_evidence_count` | 触发的证据信号数量 |
| `metadata_inspection` | EXIF、软件标签、AIGC元数据 |
| `visual_inspection` | 亮度、饱和度、调色板特征 |
| `local_feature_inspection` | 特征密度、集中度 |
| `screenshot_inspection` | 屏幕比例、边缘/文本/纯色区域指标 |
| `document_tamper_inspection` | 纸张区域分析、可疑块、LBP、梯度、噪声、ELA |
| `risk_labels` | 快速决策的分类标签 |
| `findings` | 所有人类可读的检测发现 |

## 依赖

- Python 3.8+
- Pillow
- NumPy
