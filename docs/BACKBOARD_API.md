# Backboard API Reference

> Source: https://docs.backboard.io/

## Overview

Backboard API is a unified AI infrastructure platform providing access to 2,200+ language models through a single API. It offers built-in RAG (retrieval-augmented generation), persistent memory, and function calling (tool use) capabilities.

## Base URL

```
https://app.backboard.io/api
```

## Authentication

All requests require an `X-API-Key` header:

```
X-API-Key: your_api_key
```

- Keys are generated in the Backboard Dashboard: **Settings > API Keys**
- Keys display only once upon creation
- Failed auth returns `401 Unauthorized`

## SDKs

```bash
pip install backboard-sdk          # Python
npm install backboard-sdk          # JavaScript/TypeScript
```

---

## Core Concepts

### Architecture Hierarchy

```
Assistant (system prompt, tools, embedding config)
  └── Thread (conversation session, persistent history)
       └── Message (user/assistant/tool, supports streaming)
```

- **Assistant**: AI agent with system prompt, tools, and embedding configuration
- **Thread**: Persistent conversation session maintaining full message history
- **Message**: Individual interaction within a thread (user, assistant, or tool role)
- **Memory**: Cross-thread fact persistence for an assistant
- **Document**: Uploaded file auto-indexed for RAG queries

---

## Assistants API

### Create Assistant

```
POST /assistants
```

**Request Body (JSON):**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string (1-255) | Yes | — | Assistant name |
| `description` | string\|null | No | null | System prompt (alias) |
| `system_prompt` | string\|null | No | null | Behavioral instructions |
| `tools` | array\|null | No | null | Tool/function definitions |
| `tok_k` | integer (1-100) | No | 10 | Document search top_k |
| `embedding_provider` | string\|null | No | openai | Provider: openai, google, cohere |
| `embedding_model_name` | string\|null | No | text-embedding-3-large | Embedding model |
| `embedding_dims` | integer\|null | No | 3072 | Embedding dimensions |

**Tool Definition Structure:**

```json
{
  "type": "function",
  "function": {
    "name": "function_name",
    "description": "What the function does",
    "parameters": {
      "type": "object",
      "properties": {
        "param_name": {
          "type": "string",
          "description": "Parameter description"
        }
      },
      "required": ["param_name"]
    }
  }
}
```

**Response (200):**

```json
{
  "assistant_id": "uuid",
  "name": "string",
  "description": "string|null",
  "system_prompt": "string|null",
  "tools": [],
  "tok_k": 10,
  "embedding_provider": "string|null",
  "embedding_model_name": "string|null",
  "embedding_dims": null,
  "created_at": "ISO 8601"
}
```

> **Important:** Embedding model cannot be changed after assistant creation.

### List Assistants

```
GET /assistants?skip=0&limit=100
```

Returns array of Assistant objects.

### Get Assistant

```
GET /assistants/{assistant_id}
```

### Update Assistant

```
PUT /assistants/{assistant_id}
```

**Request Body (JSON) — all fields optional:**

| Field | Type | Description |
|---|---|---|
| `name` | string\|null | New name (1-255 chars) |
| `description` | string\|null | New system prompt |
| `system_prompt` | string\|null | New system prompt (alias) |
| `tools` | array\|null | Replaces ALL existing tools |
| `tok_k` | integer\|null | Document search top_k (1-100) |

### Delete Assistant

```
DELETE /assistants/{assistant_id}
```

> Permanent. Deletes all associated threads and documents.

**Response:**

```json
{
  "message": "string",
  "assistant_id": "uuid",
  "deleted_at": "datetime"
}
```

---

## Threads API

### Create Thread

```
POST /assistants/{assistant_id}/threads
```

**Request Body:** Empty JSON `{}`

**Response (200):**

```json
{
  "thread_id": "uuid",
  "created_at": "datetime",
  "metadata_": {},
  "messages": []
}
```

### List Threads for Assistant

```
GET /assistants/{assistant_id}/threads
```

### Get Thread

```
GET /threads/{thread_id}
```

### Delete Thread

```
DELETE /threads/{thread_id}
```

---

## Messages API

### Send Message (Add Message to Thread)

```
POST /threads/{thread_id}/messages
```

**Request Body (multipart/form-data):**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `content` | string\|null | No | — | Message text |
| `llm_provider` | string\|null | No | openai | AI provider (openai, anthropic, google, etc.) |
| `model_name` | string\|null | No | gpt-4o | Model to use |
| `stream` | boolean | No | false | Enable streaming response |
| `memory` | string\|null | No | off | Memory mode: `Auto`, `On`, `off`, `Readonly` |
| `web_search` | string\|null | No | off | Web search: `Auto` or `off` |
| `send_to_llm` | string\|null | No | true | Generate AI response or save only |
| `metadata` | string\|null | No | — | Custom JSON metadata |
| `files` | array (binary) | No | [] | File attachments |

**Supported file types:** PDF, DOC(X), PPT(X), XLS(X), TXT, CSV, MD, JSON(L), XML, PY, JS, TS, JSX, TSX, HTML, CSS, CPP, C, H, JAVA, GO, RS, RB, PHP, SQL, PNG, JPG, JPEG, WEBP, GIF, BMP, TIFF

**Response (200):**

```json
{
  "message": "string",
  "thread_id": "uuid",
  "content": "string|null",
  "message_id": "uuid|null",
  "role": "user|assistant|tool",
  "status": "IN_PROGRESS|REQUIRES_ACTION|COMPLETED|FAILED|CANCELLED",
  "tool_calls": [{}],
  "run_id": "string|null",
  "memory_operation_id": "string|null",
  "retrieved_memories": [{"id": "string", "memory": "string", "score": 0.0}],
  "retrieved_files": ["string"],
  "model_provider": "string|null",
  "model_name": "string|null",
  "input_tokens": 0,
  "output_tokens": 0,
  "total_tokens": 0,
  "created_at": "datetime|null",
  "attachments": [{"document_id": "uuid", "filename": "string", "status": "string", "file_size_bytes": 0, "summary": "string|null"}],
  "timestamp": "datetime"
}
```

**Key status values:**
- `COMPLETED` — Response ready in `content`
- `REQUIRES_ACTION` — Tool calls pending, check `tool_calls` array
- `IN_PROGRESS` — Still processing
- `FAILED` / `CANCELLED` — Error states

### Streaming

Set `stream=true` in the request. Response returns Server-Sent Events. Iterate with:

```python
# Python SDK
async for chunk in client.add_message(threadId=tid, content="Hello", stream=True):
    if chunk.content:
        print(chunk.content, end="")
```

```javascript
// JavaScript SDK
const stream = await client.addMessage({ threadId: tid, content: "Hello", stream: true });
for await (const chunk of stream) {
    if (chunk.content) process.stdout.write(chunk.content);
}
```

---

## Tool Calls (Function Calling)

### Workflow

1. Define tools when creating/updating the assistant
2. Send a message — model may respond with `status: "REQUIRES_ACTION"`
3. Extract `tool_calls` from response
4. Execute your functions locally
5. Submit results via the tool outputs endpoint
6. Repeat until `status: "COMPLETED"`

### Submit Tool Outputs

```
POST /threads/{thread_id}/runs/{run_id}/submit-tool-outputs
```

**Query Parameters:**

| Field | Type | Default | Description |
|---|---|---|---|
| `stream` | boolean | false | Stream the response |

**Request Body (JSON):**

```json
{
  "tool_outputs": [
    {
      "tool_call_id": "string",
      "output": "stringified JSON result"
    }
  ]
}
```

**Response:** Same schema as Add Message response (may contain further tool calls or completed content).

### Tool Call Example (Python SDK)

```python
# 1. Define tools on assistant
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"]
        }
    }
}]

# 2. Send message, check for tool calls
response = await client.add_message(threadId=tid, content="What's the weather in NYC?", ...)

if response.status == "REQUIRES_ACTION":
    tool_outputs = []
    for tc in response.tool_calls:
        args = tc.function.parsed_arguments
        if tc.function.name == "get_weather":
            result = get_weather(args["location"])
            tool_outputs.append({
                "tool_call_id": tc.id,
                "output": json.dumps(result)
            })

    # 3. Submit tool outputs
    response = await client.submit_tool_outputs(
        threadId=tid,
        runId=response.run_id,
        tool_outputs=tool_outputs
    )
```

---

## Documents API

### Upload Document to Assistant

```
POST /assistants/{assistant_id}/documents
```

Multipart form upload. Document available across all threads.

### Upload Document to Thread

```
POST /threads/{thread_id}/documents
```

Multipart form upload. Document scoped to that thread only.

### List Documents for Assistant

```
GET /assistants/{assistant_id}/documents
```

### List Documents for Thread

```
GET /threads/{thread_id}/documents
```

### Get Document Status

```
GET /documents/{document_id}/status
```

**Response:**

```json
{
  "document_id": "uuid",
  "status": "pending|processing|indexed|error",
  "chunk_count": 0
}
```

> Wait for `status: "indexed"` before querying. Documents go through: upload > processing > chunking > embedding > indexed.

### Delete Document

```
DELETE /documents/{document_id}
```

---

## Memory API

### Memory Modes (per message)

| Mode | Behavior |
|---|---|
| `Off` | No memory (privacy-sensitive) |
| `On` | Always saves and retrieves |
| `Auto` | Intelligent save/retrieve (recommended) |
| `Readonly` | Retrieves only, no new saves |

### List Memories

```
GET /assistants/{assistant_id}/memories
```

### Add Memory

```
POST /assistants/{assistant_id}/memories
```

**Body:** `{"content": "string"}`

### Get Memory

```
GET /assistants/{assistant_id}/memories/{memory_id}
```

### Update Memory

```
PUT /assistants/{assistant_id}/memories/{memory_id}
```

### Delete Memory

```
DELETE /assistants/{assistant_id}/memories/{memory_id}
```

### Memory Stats

```
GET /assistants/{assistant_id}/memories/stats
```

### Memory Operation Status

```
GET /assistants/memories/operations/{memory_operation_id}
```

---

## Models API

### List All Models

```
GET /models
```

**Query Parameters:**

| Field | Type | Description |
|---|---|---|
| `model_type` | string | Filter: `llm` or `embedding` |
| `provider` | string | Filter by provider name |
| `supports_tools` | boolean | Filter by function calling support |
| `min_context` | integer | Minimum context window |
| `max_context` | integer | Maximum context window |
| `skip` | integer | Pagination offset (default: 0) |
| `limit` | integer | Max results (default: 100, max: 500) |

**Response:**

```json
{
  "models": [{
    "name": "string",
    "provider": "string",
    "model_type": "llm|embedding",
    "context_limit": 0,
    "max_output_tokens": null,
    "supports_tools": true,
    "api_mode": "string|null",
    "embedding_dimensions": null,
    "last_updated": "datetime|null"
  }],
  "total": 0
}
```

### Get Model

```
GET /models/{model_name}
```

### List Providers

```
GET /models/providers
```

### List Models by Provider

```
GET /models/providers/{provider}
```

### List Embedding Models

```
GET /models/embedding/all
```

**Query Parameters:**

| Field | Type | Description |
|---|---|---|
| `provider` | string | Filter by provider |
| `min_dimensions` | integer | Min embedding dimensions |
| `max_dimensions` | integer | Max embedding dimensions |
| `skip` | integer | Offset (default: 0) |
| `limit` | integer | Max results (default: 100, max: 500) |

**Response:**

```json
{
  "models": [{
    "name": "string",
    "provider": "string",
    "embedding_dimensions": 0,
    "context_limit": 0,
    "last_updated": "datetime|null"
  }],
  "total": 0
}
```

### List Embedding Providers

```
GET /models/embedding/providers
```

### Get Embedding Model

```
GET /models/embedding/{model_name}
```

---

## Model Identifiers

Models use the format `provider/model-name`:

| Use Case | Provider | Model |
|---|---|---|
| Default LLM | openai | gpt-4o |
| Gemini Flash | google | gemini-2.0-flash |
| Gemini Pro | google | gemini-2.5-pro |
| Gemini Embeddings | google | text-embedding-004 |
| Anthropic | anthropic | claude-3-opus (etc.) |

Pass `llm_provider` and `model_name` on each message to select the model.

---

## Error Responses

All endpoints return `422 Unprocessable Entity` for validation errors:

```json
{
  "detail": [{
    "loc": ["body", "field_name"],
    "msg": "error message",
    "type": "error_type"
  }]
}
```

`401 Unauthorized` for missing/invalid API key:

```json
{
  "detail": "Invalid or missing API key"
}
```

---

## SDK Quick Reference

```python
from backboard import BackboardClient

client = BackboardClient(api_key="your_key")

# Create assistant
assistant = await client.create_assistant(
    name="My Assistant",
    system_prompt="You are helpful.",
    tools=[...],
    embedding_provider="google",
    embedding_model_name="text-embedding-004",
    embedding_dims=768
)

# Create thread
thread = await client.create_thread(assistantId=assistant.assistant_id)

# Send message (non-streaming)
response = await client.add_message(
    threadId=thread.thread_id,
    content="Hello!",
    llm_provider="google",
    model_name="gemini-2.0-flash",
    stream=False,
    memory="Auto"
)
print(response.content)

# Send message (streaming)
async for chunk in client.add_message(
    threadId=thread.thread_id,
    content="Tell me more",
    llm_provider="google",
    model_name="gemini-2.5-pro",
    stream=True
):
    if chunk.content:
        print(chunk.content, end="")

# Handle tool calls
if response.status == "REQUIRES_ACTION":
    outputs = []
    for tc in response.tool_calls:
        result = execute_tool(tc.function.name, tc.function.parsed_arguments)
        outputs.append({"tool_call_id": tc.id, "output": json.dumps(result)})

    response = await client.submit_tool_outputs(
        threadId=thread.thread_id,
        runId=response.run_id,
        tool_outputs=outputs
    )
```
