<div align="center">

# 🎵 音频智能切割工具

## 基于 Silero VAD 的语音活动检测与智能分割

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-1.12+-red.svg)](https://pytorch.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

## 📖 项目简介

本项目是一个基于 **Silero VAD (Voice Activity Detection)** 技术的专业音频预处理工具。
支持将任意时长的原始音频文件自动切割成语句完整的短音频片段。


## 🖼️ 界面预览

<div align="center">
  <img width="100%" alt="image" src="https://raw.githubusercontent.com/sjsherry2025/audio-segmentation/master/src/assets/image1.png" />
</div>

<div align="center">
  <img width="100%" alt="image" src="https://raw.githubusercontent.com/sjsherry2025/audio-segmentation/master/src/assets/image2.png" />
</div>

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 |
|------|------|
| Python | >= 3.10 |
| PyTorch | >= 1.12.0 |
| Silero VAD | >= 0.1.0 |
| SoundFile | >= 0.10.0 |
| Librosa | >= 0.9.0 |

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/sjsherry2025/audio-segmentation.git
cd audio-segmentation

# 2. 创建虚拟环境（推荐）
conda create -n audio-segmentation python=3.10
conda activate audio-segmentation

# 3. 安装依赖
pip install -r requirements.txt
