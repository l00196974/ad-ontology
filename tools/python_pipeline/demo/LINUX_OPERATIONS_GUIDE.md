# Linux环境下运行Demo脚本指南

本文档介绍如何在Linux aarch64环境下运行Python流水线处理脚本。

## 1. 系统信息
- **操作系统架构**: aarch64 (ARM 64位)
- **Python版本**: 3.9.9

## 2. 依赖包处理（离线安装）

**步骤1：windows下载linux_aarch64可用的包**


```bash

屏蔽 requirements.txt

# pyyaml>=6.0
# pydantic>=2.6.0

# 最新命令
# windows下载
pip download --only-binary=:all: -i https://pypi.org/simple -r requirements.txt -d offline_packages
# linux 安装
pip3 install --find-links offline_packages/ --no-index -r requirements.txt

# 手动下载几个包并单独安装升级python到 3.12.4
pip3 install offline_packages/pyyaml-6.0.3-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl --force-reinstall --no-deps --force
pip3 install offline_packages/jiter-0.13.0-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl --force-reinstall --no-deps --force
pip3 install offline_packages/pydantic_core-2.41.5-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl --force-reinstall --no-deps --force

手工下载Linux版本的PyYAML，jiter和pydantic-core;选择cp312, aarch包
下载地址如下：
https://pypi.org/project/PyYAML/#files
https://pypi.org/project/pydantic_core/2.41.5/#files
https://pypi.org/project/jiter/0.13.0/#files

```

```bash
pip uninstall -y pydantic-core  jiter pyyaml pydantic openai
pip cache purge
```


**步骤4：安装依赖**
```bash
# 安装所有依赖
pip3 install --find-links offline_packages/ --no-index -r huawei-ad-ontology/tools/python_pipeline/requirements.txt
```

### 3. 运行Demo脚本
```bash
cd /home/apkad/ontology/huawei-ad-ontology/tools/python_pipeline
nohup python3 demo/run_demo.py &

cd /home/apkad/ontology/huawei-ad-ontology/tools/python_pipeline/data

```