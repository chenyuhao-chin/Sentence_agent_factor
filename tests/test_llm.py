#!/usr/bin/env python3
"""
Agent Factory — 端到端单体联动测试 V3.0
=========================================
双层测试架构：
  第 1 层（离线）：防爆舱空骨架 + 文件加载链 + 异常永不崩溃
  第 2 层（在线）：仅当 DEEPSEEK_API_KEY 存在时，驱动真实算力端到端出图

运行方式（终端）：
    python3 tests/test_llm.py

环境变量：
    DEEPSEEK_API_KEY    — DeepSeek API Key（可选，不设置只跑离线层）
    DEEPSEEK_BASE_URL   — DeepSeek API Base URL（可选）
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 将项目根目录加入 sys.path
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# 依赖安全导入
# ---------------------------------------------------------------------------
try:
    from core.llm_client import DeepSeekClient, EMPTY_AGENT_CONFIG
    from core.prompt_loader import PromptLoader
except ImportError as e:
    print(f"\n❌ 导入核心模块失败：{e}")
    print("   请确保项目目录结构完整。")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 用户需求（多个覆盖场景）
# ---------------------------------------------------------------------------
TEST_REQUIREMENTS = {
    "比赛路演": "帮我做一个挑战杯比赛路演PPT润色Agent",
    "代码审计": "帮我做一个高并发C++代码审查Agent，能发现内存泄漏和线程安全问题",
    "学术文献": "帮我做一个学术文献自动化管理Agent，支持APA格式引用",
}

APPROVED_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
APPROVED_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()
HAS_LIVE_API = bool(APPROVED_KEY)

# ---------------------------------------------------------------------------
# 控制台彩印工具
# ---------------------------------------------------------------------------
RESET = "\033[0m"; BOLD = "\033[1m"; GREEN = "\033[92m"
YELLOW = "\033[93m"; RED = "\033[91m"; CYAN = "\033[96m"; DIM = "\033[2m"

def ok(s=""):  return f"{GREEN}✅ {s}{RESET}"
def warn(s=""): return f"{YELLOW}⚠️  {s}{RESET}"
def fail(s=""): return f"{RED}❌ {s}{RESET}"
def hdr(s=""):  return f"{BOLD}{s}{RESET}"
def dim(s=""):  return f"{DIM}{s}{RESET}"

def banner():
    print(f"{BOLD}{'='*68}{RESET}")
    print(f"{BOLD}  🏭 Agent Factory — 端到端单体联动测试 V3.0{RESET}")
    print(f"{BOLD}{'='*68}{RESET}")
    live_status = ok("在线模式") if HAS_LIVE_API else warn("仅离线模式")
    print(f"  API 状态: {live_status}")
    print()

def section(title: str):
    print(f"\n{CYAN}━{'─'*60}{RESET}")
    print(f"{BOLD}  📋 {title}{RESET}")
    print(f"{CYAN}━{'─'*60}{RESET}\n")

def pjson(data: dict, label=""):
    if label: print(f"  🎯 {label}:\n")
    for line in json.dumps(data, indent=2, ensure_ascii=False).splitlines():
        print(f"    {dim('│')} {line}")
    print()

# ====================================================================
#  第 1 层：离线防爆舱测试（永远执行，无需 API）
# ====================================================================
def run_offline_tests():
    errors = []
    section("第 1 层 — 离线防爆舱稳定性测试")

    # ── Test 1.1：EMPTY_AGENT_CONFIG 常量完整性 ──
    print("  [1.1] EMPTY_AGENT_CONFIG 常量完整性...", end=" ")
    expected = {"agent_name", "system_prompt", "delivery_type", "auth_mode", "required_skills",
                "prompt_pack", "platforms", "memory_config", "agent_meta"}
    actual = set(EMPTY_AGENT_CONFIG.keys())
    if expected == actual:
        print(ok())
    else:
        print(fail(f"字段不匹配：期望{expected}，实际{actual}"))
        errors.append("空骨架字段不完整")

    # ── Test 1.2：_safe_json_parse 空字符串 → 空骨架 ──
    print("  [1.2] _safe_json_parse('') 应返回空骨架...", end=" ")
    try:
        from core.llm_client import DeepSeekClient as Client
        result = Client._safe_json_parse("")
        assert result == EMPTY_AGENT_CONFIG, f"结果不匹配: {result}"
        print(ok())
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"空字符串解析崩溃: {e}")

    # ── Test 1.3：_safe_json_parse 乱码 → 永不崩溃 ──
    print("  [1.3] _safe_json_parse(垃圾文本) 应不回抛...", end=" ")
    try:
        garbage = "这不是JSON#$%^&该代码无法编译"
        result = Client._safe_json_parse(garbage)
        assert result == EMPTY_AGENT_CONFIG, f"垃圾解析应返回空骨架，实际: {result}"
        print(ok())
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"垃圾文本解析崩溃: {e}")

    # ── Test 1.4：_safe_json_parse 合法 JSON 正常返回 ──
    print("  [1.4] _safe_json_parse(合法 JSON) 正常解析...", end=" ")
    try:
        valid = '{"agent_name":"test","system_prompt":"hello","delivery_type":"web","auth_mode":"user_key","required_skills":["none"]}'
        result = Client._safe_json_parse(valid)
        assert result["agent_name"] == "test"
        assert result["delivery_type"] == "web"
        print(ok())
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"合法 JSON 解析崩溃: {e}")

    # ── Test 1.5：_safe_json_parse Markdown 代码块包裹 → 自动剥离 ──
    print("  [1.5] _safe_json_parse(markdown代码块包裹) 自动剥离...", end=" ")
    try:
        wrapped = '```json\n{"agent_name":"md-test","system_prompt":"hi","delivery_type":"exe","auth_mode":"build_in","required_skills":[]}\n```'
        result = Client._safe_json_parse(wrapped)
        assert result["agent_name"] == "md-test", f"Markdown 剥离失败: {result}"
        print(ok())
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"Markdown 剥离崩溃: {e}")

    # ── Test 1.6：_validate_config 自动补全缺失字段 ──
    print("  [1.6] _validate_config 自动补全缺失字段...", end=" ")
    try:
        incomplete = {"agent_name": "half"}
        Client._validate_config(incomplete)
        for key in EMPTY_AGENT_CONFIG:
            assert key in incomplete, f"缺少字段: {key}"
        assert incomplete["delivery_type"] == "exe"
        print(ok())
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"自动补全崩溃: {e}")

    # ── Test 1.7：PromptLoader 加载 architect.md 成功 ──
    print("  [1.7] PromptLoader 加载 architect.md...", end=" ")
    try:
        loader = PromptLoader(source="local", prompt_dir="prompts")
        content = loader.load("architect")
        assert content and len(content) > 200, f"内容过短: {len(content)} 字符"
        assert "OSCAR-EX" in content or "架构师" in content, "内容不含关键标识"
        print(ok(f"({len(content)} 字符)"))
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"architect.md 加载失败: {e}")

    # ── Test 1.8：PromptLoader 加载 architect_fallback.md 成功 ──
    print("  [1.8] PromptLoader 加载 architect_fallback.md...", end=" ")
    try:
        loader = PromptLoader(source="local", prompt_dir="prompts")
        content = loader.load("architect_fallback")
        assert content and len(content) > 50, f"兜底文件内容过短: {len(content)} 字符"
        print(ok(f"({len(content)} 字符)"))
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"architect_fallback.md 加载失败: {e}")

    # ── Test 1.9：初始化 DeepSeekClient 不传 key → 应抛 ValueError ──
    print("  [1.9] 初始化客户端(无Key) 应抛 ValueError...", end=" ")
    try:
        # 临时清除环境变量
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            from core.llm_client import DeepSeekClient as Client2
            Client2(api_key="", base_url="https://example.com/v1")
            print(fail("未抛出异常"))
            errors.append("无Key初始化应抛异常但未抛")
        except ValueError:
            print(ok("正确抛出 ValueError"))
        finally:
            if old_key: os.environ["DEEPSEEK_API_KEY"] = old_key
    except Exception as e:
        print(fail(str(e)[:80]))
        errors.append(f"无Key初始化异常: {e}")

    # ── 离线层汇总 ──
    print(f"\n  {CYAN}离线层结果：{RESET}", end="")
    if errors:
        print(fail(f"{len(errors)} 项失败"))
    else:
        print(ok("全部 9 项通过"))
    return errors


# ====================================================================
#  第 2 层：在线全火力端到端测试（仅当 API Key 存在）
# ====================================================================
def run_online_tests():
    errors = []
    section("第 2 层 — 在线全火力端到端测试")

    try:
        client = DeepSeekClient(
            api_key=APPROVED_KEY,
            base_url=APPROVED_URL,
            model="deepseek-chat",
            max_retries=3,
            base_delay=1.0,
        )
        print(f"  ✅ DeepSeekClient 初始化成功")
        print(f"     Model:      {client.model}")
        print(f"     API Key:    {APPROVED_KEY[:8]}...{APPROVED_KEY[-4:]}")
        print(f"     Base URL:   {APPROVED_URL}\n")
    except Exception as e:
        print(fail(f"初始化失败: {e}"))
        return [f"在线客户端初始化崩溃: {e}"]

    for scenario, req_text in TEST_REQUIREMENTS.items():
        print(f"  🧪 测试场景：{hdr(scenario)}")
        print(f"  📝 需求：\"{req_text}\"")
        print(f"  ⏳ 请求 API...", end=" ", flush=True)

        try:
            config = client.architect(req_text)
        except Exception as e:
            print(fail(f"崩溃: {str(e)[:80]}"))
            errors.append(f"场景[{scenario}]崩溃: {e}")
            continue

        if not config.get("agent_name"):
            print(warn("空骨架（API 返回异常但未崩溃 ✅）"))
            pjson(config, "空骨架配置")
            continue
        else:
            print(ok())

        # Schema 完整性
        checks = {
            "agent_name 有值": bool(config.get("agent_name")),
            "system_prompt 长度>50": len(config.get("system_prompt", "")) > 50,
            "delivery_type 三选一": config.get("delivery_type") in ("exe", "zip", "web"),
            "auth_mode 合法": config.get("auth_mode") in ("user_key", "build_in"),
            "required_skills 是列表": isinstance(config.get("required_skills"), list),
        }
        all_good = True
        for check_name, passed in checks.items():
            icon = ok() if passed else warn()
            print(f"       {icon} {check_name}")
            if not passed:
                all_good = False
                errors.append(f"场景[{scenario}]字段 '{check_name}' 校验失败")

        if all_good:
            print(f"\n  {ok('全部字段通过')} — 完整图纸：")
            pjson(config)

    print(f"\n  {CYAN}在线层结果：{RESET}", end="")
    if errors:
        print(fail(f"{len(errors)} 项失败"))
    else:
        print(ok("全部场景通过"))
    return errors


# ====================================================================
#  main
# ====================================================================
def main():
    banner()
    all_errors = []

    # ── 第 1 层：离线防爆舱 ──
    offline_errors = run_offline_tests()
    all_errors.extend(offline_errors)

    # ── 第 2 层：在线端到端 ──
    if HAS_LIVE_API:
        online_errors = run_online_tests()
        all_errors.extend(online_errors)
    else:
        section("第 2 层 — 在线端到端测试（已跳过）")
        print(f"  {warn('未设置 DEEPSEEK_API_KEY 环境变量')}")
        print(f"  💡 设置后重新运行即可驱动真实算力端到端测试：")
        print(f"     export DEEPSEEK_API_KEY='sk-your-key'")
        print(f"     export DEEPSEEK_BASE_URL='https://api.deepseek.com/v1'")
        print()

    # ── 最终汇总 ──
    print(f"{BOLD}{'='*68}{RESET}")
    if all_errors:
        print(f"  {fail(f'测试完成 — {len(all_errors)} 项失败')}")
        for e in all_errors:
            print(f"    - {e}")
    else:
        print(f"  {ok('全部测试通过 — 零崩溃！')}")
    print(f"{BOLD}{'='*68}{RESET}")
    print()

    if not HAS_LIVE_API:
        print(f"  {warn('提示：在线层未执行。设置环境变量后可端到端测试真实 API。')}")
        return 0  # 离线通过即为成功
    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
