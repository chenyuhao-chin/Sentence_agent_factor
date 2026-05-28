#!/usr/bin/env python3
"""
Agent Factory — Coze ↔ Dify 双向转换测试
=========================================
验证 builder.py 中的转换逻辑：
  1. Coze bot.json → Dify agent.yaml
  2. Dify agent.yaml → Coze bot.json
  3. 往返一致性（roundtrip）
  4. 边界场景（空步骤、单步、多步）
  5. _parse_simple_yaml 解析器健壮性

运行方式：
    python3 tests/test_conversion.py
"""

import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from core.builder import AgentBuilder

PASS = "✅"
FAIL = "❌"
errors = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS} {name}")
    else:
        msg = f"  {FAIL} {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        errors.append(name)


# ====================================================================
#  Test 1: Coze → Dify 基本转换
# ====================================================================
def test_coze_to_dify_basic():
    print("\n📋 Test 1: Coze → Dify 基本转换")
    coze_bot = {
        "bot_name": "测试Bot",
        "description": "测试描述",
        "prompt": {"system_prompt": "你是一个测试助手"},
        "model_config": {"provider": "openai_compatible", "model": "deepseek-chat"},
        "workflow_config": {
            "mode": "sequential",
            "steps": [
                {"name": "步骤1", "prompt": "分析需求", "gate": "置信度>=0.8"},
                {"name": "步骤2", "prompt": "生成内容", "gate": "完成率>=90%"},
            ],
        },
    }

    result = AgentBuilder._convert_coze_to_dify(coze_bot)

    check("输出非空", bool(result))
    check("包含 app name", 'name: "测试Bot"' in result)
    check("包含 start 节点", 'id: "start"' in result)
    check("包含 step_1 节点", 'id: "step_1"' in result)
    check("包含 step_2 节点", 'id: "step_2"' in result)
    check("包含 answer 节点", 'id: "answer"' in result)
    check("包含模型配置", "deepseek-chat" in result)


# ====================================================================
#  Test 2: Dify → Coze 基本转换
# ====================================================================
def test_dify_to_coze_basic():
    print("\n📋 Test 2: Dify → Coze 基本转换")
    dify_yaml = """\
app:
  name: "测试Bot"
  description: "测试描述"
  mode: "chat"

version: "0.1.0"
kind: "app"

model_config:
  provider: "openai_compatible"
  model_id: "deepseek-chat"

prompt_template:
  - id: "system"
    role: "system"
    text: "你是一个测试助手"

workflow:
  graph:
    nodes:
      - id: "start"
        type: "start"
        position:
          x: 80
          y: 160
        data:
          title: "开始"
          type: "start"
          variables: []
      - id: "step_1"
        type: "llm"
        position:
          x: 430
          y: 160
        data:
          title: "步骤1"
          type: "llm"
          model:
            provider: "openai_compatible"
            name: "deepseek-chat"
          prompt_template:
            - role: "system"
              text: "分析需求"
            - role: "user"
              text: "{{#start.text}}"
      - id: "answer"
        type: "answer"
        position:
          x: 780
          y: 160
        data:
          title: "回复"
          type: "answer"
          answer: "{{#step_1.text}}"
    edges:
      - source: "start"
        target: "step_1"
      - source: "step_1"
        target: "answer"
"""
    result = AgentBuilder._convert_dify_to_coze(dify_yaml)

    check("返回 dict", isinstance(result, dict))
    check("bot_name 正确", result.get("bot_name") == "测试Bot")
    check("description 正确", result.get("description") == "测试描述")
    check("system_prompt 提取", result.get("prompt", {}).get("system_prompt") == "你是一个测试助手")
    check("workflow_config 存在", "workflow_config" in result)
    check("steps 数量", len(result.get("workflow_config", {}).get("steps", [])) == 1)


# ====================================================================
#  Test 3: 往返一致性 (Coze → Dify → Coze)
# ====================================================================
def test_roundtrip():
    print("\n📋 Test 3: 往返一致性 (Coze → Dify → Coze)")
    original = {
        "bot_name": "往返Bot",
        "description": "往返测试",
        "prompt": {"system_prompt": "你是往返助手"},
        "model_config": {"provider": "openai_compatible", "model": "deepseek-chat"},
        "workflow_config": {
            "mode": "sequential",
            "steps": [
                {"name": "分析", "prompt": "分析输入", "gate": "完整"},
                {"name": "处理", "prompt": "处理数据", "gate": "准确"},
                {"name": "输出", "prompt": "生成结果", "gate": "格式正确"},
            ],
        },
    }

    # Coze → Dify
    dify_yaml = AgentBuilder._convert_coze_to_dify(original)

    # Dify → Coze
    restored = AgentBuilder._convert_dify_to_coze(dify_yaml)

    check("bot_name 一致", restored.get("bot_name") == original["bot_name"])
    check("description 一致", restored.get("description") == original["description"])
    check(
        "system_prompt 一致",
        restored.get("prompt", {}).get("system_prompt") == original["prompt"]["system_prompt"],
    )

    orig_steps = original["workflow_config"]["steps"]
    rest_steps = restored.get("workflow_config", {}).get("steps", [])
    check("steps 数量一致", len(rest_steps) == len(orig_steps))

    for i, (o, r) in enumerate(zip(orig_steps, rest_steps)):
        check(f"step[{i}] name 一致", r.get("name") == o["name"])
        check(f"step[{i}] prompt 一致", r.get("prompt") == o["prompt"])


# ====================================================================
#  Test 4: 空步骤（单节点模式）
# ====================================================================
def test_empty_steps():
    print("\n📋 Test 4: 空步骤（单节点模式）")
    coze_single = {
        "bot_name": "简单Bot",
        "description": "简单描述",
        "prompt": {"system_prompt": "你是助手"},
        "model_config": {"provider": "openai_compatible", "model": "deepseek-chat"},
        "workflow_config": {"mode": "sequential", "steps": []},
    }

    dify_yaml = AgentBuilder._convert_coze_to_dify(coze_single)
    check("单节点 Dify 输出非空", bool(dify_yaml))
    check("包含 start 节点", 'id: "start"' in dify_yaml)
    check("包含 llm 节点", 'id: "llm"' in dify_yaml)
    check("包含 answer 节点", 'id: "answer"' in dify_yaml)

    coze_back = AgentBuilder._convert_dify_to_coze(dify_yaml)
    check("单节点还原 bot_name", coze_back.get("bot_name") == "简单Bot")


# ====================================================================
#  Test 5: _parse_simple_yaml 解析器健壮性
# ====================================================================
def test_yaml_parser():
    print("\n📋 Test 5: _parse_simple_yaml 解析器")

    # 基本 key-value
    yaml1 = "name: hello\nversion: 1"
    r1 = AgentBuilder._parse_simple_yaml(yaml1)
    check("基本 key-value", r1.get("name") == "hello" and r1.get("version") == "1")

    # 嵌套 dict
    yaml2 = "app:\n  name: test\n  mode: chat"
    r2 = AgentBuilder._parse_simple_yaml(yaml2)
    check("嵌套 dict", r2.get("app", {}).get("name") == "test")

    # 列表
    yaml3 = "items:\n  - one\n  - two\n  - three"
    r3 = AgentBuilder._parse_simple_yaml(yaml3)
    items = r3.get("items", [])
    check("基本列表", isinstance(items, list) and len(items) == 3)

    # 列表中的 dict
    yaml4 = "nodes:\n  - id: a\n    type: start\n  - id: b\n    type: end"
    r4 = AgentBuilder._parse_simple_yaml(yaml4)
    nodes = r4.get("nodes", [])
    check("列表中的 dict", isinstance(nodes, list) and len(nodes) == 2)
    if len(nodes) >= 2:
        check("列表 dict 内容", nodes[0].get("id") == "a" and nodes[1].get("id") == "b")

    # 空值 []
    yaml5 = "vars: []"
    r5 = AgentBuilder._parse_simple_yaml(yaml5)
    check("空列表 []", r5.get("vars") == [])

    # 注释和空行
    yaml6 = "# comment\n\nname: test\n\n# another\nvalue: 123"
    r6 = AgentBuilder._parse_simple_yaml(yaml6)
    check("注释过滤", r6.get("name") == "test" and r6.get("value") == "123")

    # 复杂嵌套：模拟 Dify 工作流
    yaml7 = """\
workflow:
  graph:
    nodes:
      - id: "start"
        type: "start"
        data:
          title: "开始"
      - id: "llm"
        type: "llm"
        data:
          title: "AI"
      - id: "answer"
        type: "answer"
        data:
          title: "回复"
"""
    r7 = AgentBuilder._parse_simple_yaml(yaml7)
    wf_nodes = r7.get("workflow", {}).get("graph", {}).get("nodes", [])
    check("复杂嵌套 nodes 数量", len(wf_nodes) == 3, f"实际: {len(wf_nodes)}")
    if len(wf_nodes) >= 3:
        check("复杂嵌套 node ids",
              wf_nodes[0].get("id") == "start"
              and wf_nodes[1].get("id") == "llm"
              and wf_nodes[2].get("id") == "answer")


# ====================================================================
#  Test 6: _build_coze_bot_fallback 输出合法 JSON
# ====================================================================
def test_coze_fallback_json():
    print("\n📋 Test 6: _build_coze_bot_fallback 输出合法 JSON")
    builder = AgentBuilder({
        "agent_name": "测试Agent",
        "system_prompt": "你是测试助手",
        "required_skills": ["分析"],
    })
    fallback = builder._build_coze_bot_fallback("测试Agent")
    try:
        parsed = json.loads(fallback)
        check("fallback 是合法 JSON", True)
        check("fallback 有 bot_name", parsed.get("bot_name") == "测试Agent")
    except json.JSONDecodeError as e:
        check("fallback 是合法 JSON", False, str(e))


# ====================================================================
#  Test 7: build_agent_meta 输出
# ====================================================================
def test_build_agent_meta():
    print("\n📋 Test 7: build_agent_meta 输出")
    config = {
        "agent_name": "元数据测试Agent",
        "description": "测试元数据生成",
        "system_prompt": "你是元数据测试助手，拥有分析和生成能力。",
        "delivery_type": "zip",
        "required_skills": ["分析", "生成"],
        "skills": [
            {"name": "分析", "type": "analysis", "description": "数据分析能力"},
            {"name": "生成", "type": "operation", "description": "内容生成能力"},
        ],
        "memory_config": {"type": "short_term", "max_turns": 5, "persist_strategy": "session_only"},
        "workflow_steps": [
            {"step_id": "step_1", "name": "分析", "prompt": "分析输入", "gate": "完整"},
        ],
    }
    builder = AgentBuilder(config, delivery_type="zip")
    meta_json = builder.build_agent_meta()
    meta = json.loads(meta_json)

    check("meta 有 name", meta.get("name") == "元数据测试Agent")
    check("meta 有 version", "version" in meta)
    check("meta 有 platforms", isinstance(meta.get("platforms"), list))
    check("meta 有 skills", len(meta.get("skills", [])) == 2)
    check("meta 有 memory_config", "memory_config" in meta)
    check("meta 有 prompt_pack", "prompt_pack" in meta)
    pp = meta.get("prompt_pack", {})
    check("prompt_pack 有 system", bool(pp.get("system")))
    check("prompt_pack 有 tool", bool(pp.get("tool")))
    check("prompt_pack 有 memory", bool(pp.get("memory")))
    check("prompt_pack 有 output", bool(pp.get("output")))
    check("meta 有 workflow_steps", len(meta.get("workflow_steps", [])) == 1)


# ====================================================================
#  main
# ====================================================================
def main():
    print("=" * 60)
    print("  🔄 Agent Factory — Coze ↔ Dify 转换测试")
    print("=" * 60)

    test_coze_to_dify_basic()
    test_dify_to_coze_basic()
    test_roundtrip()
    test_empty_steps()
    test_yaml_parser()
    test_coze_fallback_json()
    test_build_agent_meta()

    print(f"\n{'=' * 60}")
    if errors:
        print(f"  {FAIL} 测试完成 — {len(errors)} 项失败")
        for e in errors:
            print(f"    - {e}")
        return 1
    else:
        print(f"  {PASS} 全部测试通过 — 零崩溃！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
