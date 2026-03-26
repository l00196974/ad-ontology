#!/usr/bin/env python3
"""
运行demo脚本 - 针对data目录下的输入文件批量运行处理
"""

import os
import subprocess
import sys
from pathlib import Path
import shutil


def prepare_config():
    """
    从固定目录复制config.yaml文件覆盖当前配置
    """
    source_config = "./config/config.yaml"
    target_config = "./config.yaml"

    if os.path.exists(source_config):
        print("正在准备配置文件.")
        shutil.copy2(source_config, target_config)
        print(f"已从 {source_config} 复制配置文件到 {target_config}")
    else:
        print(f"警告: 源配置文件 {source_config} 不存在，跳过复制")
        print("注意: 当前配置文件可能包含敏感信息，请确认后再运行")


def run_single_case(input_file, prompt_template, output_file=None):
    """
    运行单个案例

    Args:
        input_file: 输入CSV文件名
        prompt_template: 使用的prompt模板名称
        output_file: 输出CSV文件名，如果不提供则自动生成
    """
    # 检查输入文件是否存在和是否为空
    input_path = Path(f"./data/{input_file}")
    if not input_path.exists():
        print(f"[SKIP] 输入文件不存在: {input_file},${input_path.absolute()}")
        return False

    if input_path.stat().st_size == 0:
        print(f"[SKIP] 输入文件为空: {input_file}")
        return False

    if output_file is None:
        # 从输入文件名生成输出文件名（替换input为output）
        stem = Path(input_file).stem
        output_file = stem.replace("_input", "_output") + ".csv"

    print(f"正在运行案例: {input_file} -> {output_file} (使用模板: {prompt_template})")

    cmd = [
        sys.executable, "-m", "src.pipeline.main", "run",
        "--input", f"./data/{input_file}",
        "--output", f"./data/{output_file}",
        "--prompt", prompt_template
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"[OK] 成功完成: {input_file}")
        print(f"  输出: {output_file}")
        if result.stdout:
            print(f"  标准输出: {result.stdout[-500:]}")  # 显示最后500字符
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] 执行失败: {input_file}")
        print(f"  错误代码: {e.returncode}")
        if e.stderr:
            print(f"  标准错误: {e.stderr}")
        return False


def main():
    """主函数 - 运行所有测试案例"""
    # 在运行案例前准备配置文件
    prepare_config()

    print("\n注意事项:")
    print("- 当前配置文件可能包含敏感信息，请确认后再运行")
    print("- 确保数据文件非空且格式正确")
    print("- 确保已正确设置API密钥等认证信息")
    print("="*60)

    print("开始运行Demo脚本")
    print("="*60)

    # 定义案例列表
    cases = [
        {
            "input_file": "game_positive_input.csv",
            "prompt_template": "game_analysis",
            "description": "游戏分析 - 正面案例"
        },
        {
            "input_file": "game_negative_input.csv",
            "prompt_template": "game_analysis",
            "description": "游戏分析 - 负面案例"
        },
        {
            "input_file": "jinrong_positive_input.csv",
            "prompt_template": "jinrong_analysis",
            "description": "金融分析 - 正面案例"
        },
        {
            "input_file": "jinrong_negative_input.csv",
            "prompt_template": "jinrong_analysis",
            "description": "金融分析 - 负面案例"
        }
    ]

    success_count = 0
    total_count = len(cases)

    for case in cases:
        print(f"\n[{cases.index(case)+1}/{total_count}] {case['description']}")
        print("-" * 40)

        success = run_single_case(
            input_file=case["input_file"],
            prompt_template=case["prompt_template"]
        )

        if success:
            success_count += 1

    print("\n" + "="*60)
    print(f"运行完成: {success_count}/{total_count} 个案例成功")

    if success_count != total_count:
        print(f"警告: {total_count - success_count} 个案例失败或跳过")
        if success_count == 0:
            print("提示: 如果因为配置或数据文件问题跳过所有案例，请先准备必要的文件")
    else:
        print("所有案例均成功运行！")


if __name__ == "__main__":
    main()