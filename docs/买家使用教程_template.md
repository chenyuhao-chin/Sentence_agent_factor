# 🤖 {AGENT_NAME} — 使用说明书

> **你的专属 AI 助手，已经为你调教完毕。**
> 只需要说一句话告诉它任务，它立刻帮你干活。
>
> 无需编程、无需部署、无需理解任何技术原理。

---

## 🌟 你拿到了什么？

你拿到的 ZIP 压缩包里，是一个**已经训练好的、专注解决 `{AGENT_SCENARIO}` 问题的专属 AI 助手**。

它不是一个开发工具，而是一个**即开即用的生产力工具**——就像你买了一台咖啡机，不需要知道里面的锅炉怎么工作，放豆子按开关就有咖啡喝。

### 它能做什么？

| 你输入 | 它输出 |
|--------|--------|
| "帮我润色这段路演PPT的讲稿" | ✅ 优化后的专业话术 |
| "给这段文案加个更吸引人的开头" | ✅ 3 个不同风格的备选 |
| "把这段技术术语翻译成投资人能听懂的话" | ✅ 大白话版本 |
| ...任何 `{AGENT_SCENARIO}` 相关的需求 | ✅ 高质量结果 |

### 适用人群

- 🏆 **参赛学生**：比赛路演前快速优化讲稿
- 💼 **职场人士**：日常文案、汇报材料快速处理
- 🛒 **知识付费买家**：到手即用，无需二次学习
- 🔬 **科研人员**：学术表达润色、摘要优化

---

## 🛠️ 环境准备（必读！跳过这步会报错）

> ⏱️ 只需要做一次，以后每次直接使用。

### 检查你的电脑有没有 Python

**Windows 用户：**
1. 按 `Win + R`，输入 `cmd`，回车
2. 在弹出的黑框里输入：
```bash
python --version
```
3. 如果你看到类似 `Python 3.9.x`、`Python 3.10.x`、`Python 3.11.x` 或 `Python 3.12.x` 这样的输出 → ✅ **合格，继续下一步**
4. 如果看到：
   - `'python' 不是内部或外部命令`
   - 或者版本号是 `Python 2.x`（比如 `Python 2.7`）
   
   → ❌ **需要安装 Python，请看下面的教程**

---

<details>
<summary><strong>🖱️ 点击展开：Winodws 安装 Python 详细教程</strong></summary>

1. 打开浏览器，访问 https://www.python.org/downloads/
2. 点击大大的黄色 **Download Python 3.12.x** 按钮
3. 下载完成后，**双击**安装包
4. ⚠️ **最关键的一步**：在安装窗口的**最底部**，有一个复选框：
   ```
   ☐ Add Python 3.12 to PATH
   ```
   **→ 必须勾选上！** 变成：
   ```
   ☑ Add Python 3.12 to PATH
   ```
5. 点击 **Install Now**，等待安装完成
6. 安装完成后，**重启**你的命令行窗口（关掉重新打开）
7. 再次输入 `python --version`，如果显示版本号 → ✅ 成功

> 💡 **为什么一定要勾选 Add to PATH？**
> 如果没有勾选，你的电脑就不知道 `python` 这个命令在哪里，会一直报错。**这是 90% 新手退款的原因，勾上它就能避免。**
</details>

---

**Mac 用户：**
```bash
# 打开终端（Command + 空格，搜索"终端"）
python3 --version
```
如果显示版本号 → ✅ 合格

**Linux 用户：**
```bash
python3 --version
```
如果显示版本号 → ✅ 合格

---

### 安装依赖包

```bash
# Windows 用户用这个：
pip install -r requirements.txt

# Mac / Linux 用户用这个：
pip3 install -r requirements.txt
```

> ⏳ 等待 1-2 分钟，看到 `Successfully installed openai` 就成功了。

---

## 🔑 配置你的 API Key

{AGENT_NAME} 需要连接一个 AI 模型来工作，你需要准备一个 API Key。

### 第一步：获取 API Key（以 DeepSeek 为例）

1. 打开 https://platform.deepseek.com
2. 注册账号 → 登录
3. 找到「API Keys」页面
4. 点击「创建 API Key」，复制那串以 `sk-` 开头的密钥

> 🔑 **其他模型也支持（任选一个即可）：**
>
> | 模型 | 注册地址 | 初始免费额度 |
> |------|---------|-------------|
> | 通义千问 Qwen | https://dashscope.aliyun.com | 很多 |
> | 智谱 GLM | https://open.bigmodel.cn | 送体验金 |
> | 百度千帆 | https://cloud.baidu.com | 按量付费 |

### 第二步：填写配置

1. 在你解压后的文件夹里，找到 `.env.example` 文件
2. **复制一份**，重命名为 `.env`（注意前面有个点）
3. 用记事本打开 `.env`，填入你的信息：

```bash
MY_API_KEY=sk-这里改成你的API Key      ← 最重要的！填你刚才复制的那串
MY_BASE_URL=https://api.deepseek.com/v1   ← 模型官方地址
MY_MODEL_NAME=deepseek-chat               ← 模型名称
```

**不同模型的填写示例：**

```bash
# ─── 如果你用 DeepSeek ───
MY_API_KEY=sk-你的key
MY_BASE_URL=https://api.deepseek.com/v1
MY_MODEL_NAME=deepseek-chat

# ─── 如果你用 通义千问 Qwen ───
MY_API_KEY=sk-你的key
MY_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MY_MODEL_NAME=qwen-turbo

# ─── 如果你用 智谱 GLM ───
MY_API_KEY=你的key
MY_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MY_MODEL_NAME=glm-4

# ─── 如果你用 中转API ───
MY_API_KEY=你的key
MY_BASE_URL=你的中转地址
MY_MODEL_NAME=你购买的模型名
```

> ⚠️ **安全警告**：
> - `.env` 文件包含你的 API Key，**不要**分享给任何人
> - **不要**把 `.env` 上传到网盘、GitHub 等公开平台
> - 如果不小心泄露了，去官网删除旧 Key 重新生成一个

---

## 🚀 开始使用

### 方式一：一句话指令（推荐）

打开终端，进入解压后的文件夹，输入：

```bash
python3 {AGENT_FILENAME}.py "你的具体需求"
```

**实际例子：**
```bash
python3 {AGENT_FILENAME}.py "帮我润色这段路演讲稿，让它更有感染力"
```

> 💡 **写得越具体，输出越精准！**
>
> ✅ 好的例子：
> - "帮我优化这段项目介绍的措辞，面向投资人"
> - "把这段 500 字的技术描述改写成 200 字的电梯演讲"
> - "检查这段文案是否有逻辑漏洞，指出并修正"
>
> ❌ 不够好的例子：
> - "帮我看看"
> - "润色一下"

### 方式二：纯交互模式

直接运行，不跟任何参数：

```bash
python3 {AGENT_FILENAME}.py
```

然后程序会进入对话模式，你可以一句一句地跟它聊天，它会记住上下文。

### 💡 进阶小技巧：拖拽文件

如果你有一个**本地文件**（比如 PPT 草稿、Word 文档、代码文件），想让它帮你处理：

**Windows 用户：**
```bash
# 直接把文件从桌面拖到这个终端窗口，路径会自动填入
python3 {AGENT_FILENAME}.py "帮我分析这个文件的内容" 把文件拖到这里
```

**Mac 用户同样：**
```bash
python3 {AGENT_FILENAME}.py "帮我总结这个文档" 把文件拖到这里
```

> 拖拽文件到终端窗口，文件的完整路径会自动粘贴上去，不需要手动打字。

---

## 💰 关于费用（重要！请仔细阅读）

{AGENT_NAME} 本身**完全免费**，你只需要承担 AI 模型调用的 Token 费用。

### 什么是 Token 费用？

- AI 模型按"字数"收费，这个计费单位叫 Token
- 1 个汉字大约 = 1~2 个 Token
- 每次提问和回答都会消耗 Token

### 大概要花多少钱？

以 DeepSeek 为例：
| 使用量 | 预估费用 |
|--------|---------|
| 偶尔用用（每天几十次） | 几乎免费，几分钱 |
| 频繁使用（每天几百次） | 几块钱/月 |
| 重度使用（千次以上/天） | 几十块/月 |

> 绝大多数用户一个月花不到一杯奶茶钱。

### 如何设置费用上限（强烈建议！）

去 API 提供商的官网后台：

1. **DeepSeek**: 设置 → 消费限制 → 开启「月消费上限」
2. **通义千问**: 费用中心 → 设置预算告警
3. **其他模型**: 找「预算控制」或「Usage Limit」

> 建议设置每月 **20 元** 上限，永远不会超支。

---

## ❓ 常见问题

**Q：报错 `'python' 不是内部或外部命令`？**
A：Python 没装或者没加到 PATH。回看上面的「环境准备」章节，**务必勾选 Add Python to PATH**。

**Q：报错 `No module named 'openai'`？**
A：忘记安装依赖了。运行 `pip install -r requirements.txt`。

**Q：运行后没有输出任何内容？**
A：检查 `.env` 文件中的 API Key 和 Base URL 是否正确填写。

**Q：提示 `Authentication Error`？**
A：API Key 错误或已过期。回到官网重新生成一个 Key。

**Q：输出的结果质量不好？**
A：把你的需求写得更具体一些。比如不写"帮我润色"，而写"帮我把这段话改成更正式、适合路演场合的商务风格"。

**Q：会不会突然扣很多钱？**
A：去 API 后台设置月消费上限（建议 20 元），到了自动停止，永远不会超支。

**Q：能不能在手机上运行？**
A：理论上可以用 Termux，但我们推荐在电脑上使用以获得最佳体验。

---

## 📞 技术支持

- 📧 遇到问题请向你的卖家反馈
- 🌐 更多 AI 工具和资讯，请关注卖家最新发布

---

<p align="center">
  <em>你的专属 AI 助手，开机即用 — <strong>{AGENT_NAME}</strong></em>
</p>
