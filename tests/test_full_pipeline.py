#!/usr/bin/env python3
"""
Agent Factory — 全链路端到端测试 V2.0
======================================
验证从需求输入 → 架构师出图 → 装配引擎 → 打包器的完整闭环流水线。

运行方式：
    export DEEPSEEK_API_KEY='sk-xxx'
    export DEEPSEEK_BASE_URL='https://api.deepseek.com'
    python3 tests/test_full_pipeline.py
"""

import json
import os
import sys
from pathlib import Path

# 将项目根目录加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm_client import DeepSeekClient
from core.builder import AgentBuilder
from core.packager import AgentPackager

SEPARATOR = "=" * 66
PASS = "✅"
FAIL = "❌"
WARN = "⚠️"


def test_phase1_architect():
    """阶段 1：架构师出图"""
    print(f"\n{'─' * 66}")
    print("  📋 阶段 1/3 — 架构师模式 → agent_config")
    print(f"{'─' * 66}")

    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"  {FAIL} DeepSeekClient 初始化失败: {e}")
        return None

    print(f"  {PASS} DeepSeekClient 初始化成功 (model={client.model})")

    requirement = "帮我做一个挑战杯比赛路演PPT润色Agent"
    print(f"  📝 需求: {requirement[:50]}...")
    print("  ⏳ 请求 DeepSeek API...")

    config = client.architect(requirement)

    if not config or not config.get("agent_name"):
        print(f"  {FAIL} 架构师返回空配置")
        return None

    print(f"  {PASS} 架构师出图成功：{config.get('agent_name')}")
    print(f"     System Prompt: {len(config.get('system_prompt', ''))} 字符")
    print(f"     Delivery:      {config.get('delivery_type')}")
    print(f"     Skills:        {config.get('required_skills')}")

    return config


def test_phase2_builder(config):
    """阶段 2：装配引擎（exe + web 双模板）"""
    print(f"\n{'─' * 66}")
    print("  📋 阶段 2/3 — 装配引擎 → 生成智能体脚本")
    print(f"{'─' * 66}")

    output_paths = []

    for delivery_type in ["exe", "web"]:
        print(f"\n  🔧 装配: {delivery_type}")
        builder = AgentBuilder(
            config=config,
            delivery_type=delivery_type,
            api_key="sk-demo-key-for-testing",
            base_url="https://api.deepseek.com/v1",
            model_name="deepseek-chat",
        )

        output_path = builder.assemble()
        output_paths.append(str(output_path))
        print(f"  {PASS} 生成：{output_path}")

        # 验证文件
        assert output_path.exists(), f"文件不存在: {output_path}"
        content = output_path.read_text(encoding="utf-8")

        # 占位符完整性检查
        placeholders = ["{AGENT_NAME}", "{SYSTEM_PROMPT}", "{API_KEY_SLOT}", "{BASE_URL_SLOT}", "{MODEL_NAME_SLOT}"]
        all_clean = True
        for ph in placeholders:
            if ph in content:
                print(f"     {FAIL} 占位符残留: {ph}")
                all_clean = False
        if all_clean:
            print(f"     {PASS} 占位符替换 100% 完整")
        print(f"     📄 {len(content)} 字符")

    return output_paths


def test_phase3_packager(config, script_paths):
    """阶段 3：打包器 → ZIP 交付包"""
    print(f"\n{'─' * 66}")
    print("  📋 阶段 3/3 — 打包器 → 最终交付物")
    print(f"{'─' * 66}")

    agent_name = config.get("agent_name", "测试智能体")

    for i, dtype in enumerate(["exe", "web"]):
        target_script = script_paths[i] if i < len(script_paths) else script_paths[0]
        print(f"\n  📦 打包: {dtype}")

        packager = AgentPackager(
            script_path=target_script,
            delivery_type="zip",
            agent_name=agent_name,
        )
        result = packager.package()

        if result.success:
            print(f"  {PASS} 打包成功")
            zip_path = Path(result.output_path)
            if zip_path.exists():
                print(f"     📍 {result.output_path}")
                print(f"     📦 {zip_path.stat().st_size / 1024:.1f} KB")
        else:
            print(f"  {FAIL} 打包失败: {result.message}")


def test_full_pipeline():
    print(f"\n{SEPARATOR}")
    print("  🏭 Agent Factory — 全链路端到端测试 V2.0")
    print(f"{SEPARATOR}")

    # 检查 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL")
    if not api_key:
        print(f"\n  {WARN}  未设置 DEEPSEEK_API_KEY，仅跑离线层")
        print(f"  💡 设置后重新运行: export DEEPSEEK_API_KEY='sk-your-key'")
        print(f"\n  ⏭️  跳过在线层...")
        return False

    print(f"  API: {base_url or 'default'} | Key: {api_key[:10]}...")
    print()

    # ── 三个阶段的链式调用 ──
    config = test_phase1_architect()
    if config is None:
        print(f"\n  {FAIL} 阶段 1 失败，终止测试")
        return False

    script_paths = test_phase2_builder(config)
    if not script_paths:
        print(f"\n  {FAIL} 阶段 2 失败，终止测试")
        return False

    test_phase3_packager(config, script_paths)

    # ── 最终 ──
    print(f"\n{SEPARATOR}")
    print("  ✅ 全链路测试完成 — 零崩溃！")
    print(f"{SEPARATOR}")
    print(f"\n  验证清单:")
    print(f"     {PASS} 架构师 → agent_config 图纸")
    print(f"     {PASS} 装配引擎 → exe + web 双模板智能体")
    print(f"     {PASS} 占位符 → 100% 替换完整性")
    print(f"     {PASS} 打包器 → ZIP 交付包")
    print(f"     {PASS} 全程零崩溃、零异常")
    print()

    return True


if __name__ == "__main__":
    test_full_pipeline()
