# Demo运行脚本

此脚本用于批量运行不同场景的案例，针对data目录下的输入文件进行处理。

## 使用方法

从项目根目录（python_pipeline）运行脚本：
```bash
python demo/run_demo.py
```

## Linux环境运行指南

### 系统要求
- Linux aarch64架构
- Python 3.9.9

详情请参见 `LINUX_OPERATIONS_GUIDE.md`。

### 3. 配置 config/config.yaml
cp config_data/config.yaml huawei-ad-ontology/tools/python_pipeline/config/

### 4. 数据文件 data/
cp config_data/data/* huawei-ad-ontology/tools/python_pipeline/data/

### 5. 运行命令
在Linux环境下使用以下命令运行：
```bash
cd /home/apkad/ontology/huawei-ad-ontology/tools/python_pipeline
python3 demo/run_demo.py
```

## 运行的案例脚本会自动运行以下4个案例：
1. **游戏分析 - 正面案例**
   - 输入: `data/game_positive_input.csv`
   - 模板: `game_analysis`
   - 输出: `data/game_positive_output.csv`

2. **游戏分析 - 负面案例**
   - 输入: `data/game_negative_input.csv`
   - 模板: `game_analysis`
   - 输出: `data/game_negative_output.csv`

3. **金融分析 - 正面案例**
   - 输入: `data/jinrong_positive_input.csv`
   - 模板: `jinrong_analysis`
   - 输出: `data/jinrong_positive_output.csv`

4. **金融分析 - 负面案例**
   - 输入: `data/jinrong_negative_input.csv`
   - 模板: `jinrong_analysis`
   - 输出: `data/jinrong_negative_output.csv`

每个案例会使用相应的prompt模板对输入数据进行处理，并生成对应的输出文件。