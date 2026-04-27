# ai/agent/clients/ — 레거시 (LangChain으로 대체됨)

> **이 디렉터리의 Python 구현은 제거되었습니다.**  
> LangChain 전환(2026-04-22) 이후 `ai/agent/llm.py`가 역할을 대신합니다.

---

## 대체 구조

| 구 파일 | 대체 |
|---------|------|
| `clients/base.py` (`AgentClient`, `AgentUnavailableError`, `ToolCall`) | LangChain `BaseChatModel` + `.with_fallbacks()` |
| `clients/openai.py` (`OpenAIAgentClient`) | `ai/agent/llm.py` → `build_primary_llm()` (`ChatOpenAI`) |
| `clients/claude.py` (`ClaudeAgentClient`) | `ai/agent/llm.py` → `build_fallback_llm()` (`ChatAnthropic`) |

## LangChain 폴백 체인

```python
# ai/agent/llm.py
primary = build_primary_llm()   # ChatOpenAI(base_url=PRIMARY_LLM_BASE_URL, ...)
fallback = build_fallback_llm() # ChatAnthropic(...) | None

# 사용 측 (executor.py)
llm = primary.bind_tools(tools).with_fallbacks([fallback.bind_tools(tools)])
```

폴백은 LangChain `.with_fallbacks()` 체인으로 처리합니다.  
Primary가 예외를 던지면 다음 LLM이 자동으로 재시도합니다.

## Provider 전환 (.env만 수정)

```env
# OpenRouter
PRIMARY_LLM_BASE_URL=https://openrouter.ai/api/v1
PRIMARY_LLM_API_KEY=sk-or-...
PRIMARY_LLM_MODEL=google/gemma-4-31b-it

# Ollama (로컬)
PRIMARY_LLM_BASE_URL=http://localhost:11434/v1
PRIMARY_LLM_API_KEY=ollama
PRIMARY_LLM_MODEL=qwen3:8b

# OpenAI 직접
PRIMARY_LLM_BASE_URL=https://api.openai.com/v1
PRIMARY_LLM_API_KEY=sk-...
PRIMARY_LLM_MODEL=gpt-4o
```

`build_primary_llm()`은 `ChatOpenAI`를 사용하므로 `/v1/chat/completions` 호환 provider라면  
`PRIMARY_LLM_BASE_URL`만 교체하면 됩니다.
