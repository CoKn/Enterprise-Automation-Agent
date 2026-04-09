# Enterprise Automation Agent

FastAPI-based agent runtime that plans and executes tasks through MCP tools.

The app currently uses:

- OpenAI chat completions for planning and reasoning
- MCP servers for tool execution
- A tree-based planning context with BFS traversal

## Requirements

- Python 3.13+
- `uv` installed
- An OpenAI API key
- At least one running MCP server (default: local web search server on port 8003)

## Installation

1. Create the virtual environment with `uv`:

    ```bash
    uv venv --python 3.13
    source .venv/bin/activate
    ```

2. Install dependencies:

    ```bash
    uv sync
    ```

3. Create a `.env` file in the project root:

    ```env
    OPENAI_API_KEY=your_openai_api_key
    LLM_MODEL=gpt-4.1-mini
    ```

`LLM_MODEL` must be a model name available to your OpenAI account.

## Configure MCP Endpoints

MCP endpoints are configured in [agent/config.json](agent/config.json).

Current default config:

```json
[
  {
    "id": "Websearch_Scraping",
    "transport": "streamable-http",
    "url": "http://localhost:8003/mcp"
  }
]
```

Notes:

- `id` is used as the namespace prefix for tool names.
- Full tool names are namespaced as `<id>.<tool_name>`.

## Start MCP Server(s)

Start the bundled websearch MCP server first:

```bash
source .venv/bin/activate
uv run python tools/websearch.py
```

It serves MCP over streamable HTTP at `http://localhost:8003/mcp`.

## Start the Agent API

In a second terminal:

```bash
source .venv/bin/activate
uv run python -m agent.main
```

The API starts on `http://localhost:8090`.

## Quick API Usage

Check available tools:

```bash
curl http://localhost:8090/v1/tools
```

Run the agent:

```bash
curl -X POST http://localhost:8090/v1/agent \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Tell me something about fractals."}'
```

Get one tool spec:

```bash
curl http://localhost:8090/v1/tools/Websearch_Scraping.search_web
```

## Runtime Flow

1. API receives a prompt at `POST /v1/agent`.
2. A root planning node is created.
3. Planner generates a node tree with tool steps.
4. React loop runs: `plan -> act -> observe`.
5. MCP tool calls execute through the configured endpoint(s).
