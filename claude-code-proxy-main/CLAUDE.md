# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **FastAPI-based HTTP API proxy server** that translates between Claude's Anthropic API format and OpenAI's API format. It enables Claude Code to work with any OpenAI-compatible LLM provider (OpenAI, Azure OpenAI, Ollama, etc.).

**Core Functionality:**
- Receives requests in Claude API format (`/v1/messages`)
- Converts to OpenAI format
- Forwards to configured LLM provider
- Converts responses back to Claude format
- Supports streaming, tool calling, and multimodal inputs

## Development Commands

### Environment Setup

```bash
# Install dependencies (recommended)
uv sync

# Or using pip
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Running the Server

```bash
# Direct run (development)
python start_proxy.py

# Using UV
uv run claude-code-proxy

# With hot reload for development
uvicorn src.main:app --reload --host 0.0.0.0 --port 8082

# Docker
docker compose up -d
docker compose -f docker-compose.dev.yml up --build  # With hot reload
```

### Testing

```bash
# Run test suite
pytest tests/

# Run specific test file
pytest tests/test_main.py

# Test cancellation functionality
python test_cancellation.py

# Manual integration test
python src/test_claude_to_openai.py
```

### Code Quality

```bash
# Format code
uv run black src/
uv run isort src/

# Type checking
uv run mypy src/
```

### Binary Packaging

```bash
# Create standalone binary
uv run pyinstaller --onefile --name claude-code-proxy-single src/main.py

# Create directory version (for development)
uv run pyinstaller claude-proxy.spec
```

## Architecture

### Directory Structure

```
src/
├── main.py                 # FastAPI app entry point
├── core/
│   ├── config.py          # Configuration management (environment variables)
│   ├── client.py          # HTTP client for provider APIs (with cancellation)
│   ├── model_manager.py   # Model name mapping logic
│   ├── logging.py         # Logging configuration
│   └── constants.py       # Application constants
├── api/
│   └── endpoints.py       # FastAPI route handlers
├── conversion/
│   ├── request_converter.py   # Claude → OpenAI format conversion
│   └── response_converter.py  # OpenAI → Claude format conversion
└── models/
    ├── claude.py          # Pydantic models for Claude API format
    └── openai.py          # Pydantic models for OpenAI API format
```

### Request Flow

```
1. Claude Client sends request to /v1/messages (Claude format)
   ↓
2. src/api/endpoints.py validates API key
   ↓
3. src/conversion/request_converter.py converts to OpenAI format
   ↓
4. src/core/model_manager.py maps Claude model to provider model
   ↓
5. src/core/client.py forwards to provider API
   ↓
6. src/conversion/response_converter.py converts response back to Claude format
   ↓
7. Response sent to client (with SSE streaming if enabled)
```

### Key Components

**Configuration System** (`src/core/config.py`)
- Loads all environment variables from `.env`
- Validates required settings (OPENAI_API_KEY)
- Supports client API key validation via ANTHROPIC_API_KEY
- Custom headers via CUSTOM_HEADER_* variables
- Model mapping configuration (BIG_MODEL, MIDDLE_MODEL, SMALL_MODEL)

**Model Mapping** (`src/core/model_manager.py`)
- Claude model names are mapped to provider models based on patterns:
  - Models containing "haiku" → `SMALL_MODEL` (default: gpt-4o-mini)
  - Models containing "sonnet" → `MIDDLE_MODEL` (default: gpt-4o)
  - Models containing "opus" → `BIG_MODEL` (default: gpt-4o)

**HTTP Client** (`src/core/client.py`)
- Async HTTP client for provider API communication
- Supports request cancellation when client disconnects
- Connection pooling and timeout management
- Custom header injection

**API Endpoints** (`src/api/endpoints.py`)
- `POST /v1/messages` - Main chat completion endpoint
- `POST /v1/messages/count_tokens` - Token counting
- `GET /health` - Health check
- `GET /test-connection` - Connection testing

### Environment Variables

**Required:**
- `OPENAI_API_KEY` - API key for the target LLM provider

**Authentication:**
- `ANTHROPIC_API_KEY` - If set, validates client API keys (recommended for security)

**Model Configuration:**
- `BIG_MODEL` - Model for opus requests (default: gpt-4o)
- `MIDDLE_MODEL` - Model for sonnet requests (default: BIG_MODEL value)
- `SMALL_MODEL` - Model for haiku requests (default: gpt-4o-mini)

**API Settings:**
- `OPENAI_BASE_URL` - Provider API base URL (default: https://api.openai.com/v1)
- `AZURE_API_VERSION` - Azure OpenAI API version
- `REQUEST_TIMEOUT` - Request timeout in seconds (default: 90)
- `MAX_RETRIES` - Maximum retry attempts (default: 2)

**Server Configuration:**
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 8082)
- `LOG_LEVEL` - Logging level (default: INFO)

**Provider-Specific:**
- `API_PROVIDER` - "openai" or "lmp" for LMP platform
- `LMP_API_VERSION` - "" for V1, "V2" for V2 streaming format (LMP only)

**Tool Choice Configuration:**
- `FORCE_TOOL_CHOICE` - When to auto-add tool_choice: "auto" (default), "none", "required"
- `DEFAULT_TOOL_CHOICE` - Tool name to use when auto-generating tool_choice (empty = first tool)

**Custom Headers:**
- `CUSTOM_HEADER_*` - Custom HTTP headers (e.g., CUSTOM_HEADER_ACCEPT="application/json")

### Design Patterns

**Async/Await Throughout:**
- All I/O operations use async/await for high concurrency
- FastAPI's native async support
- Async HTTP client in `src/core/client.py`

**Pydantic for Validation:**
- Request/response models in `src/models/`
- Automatic validation and serialization
- Type safety throughout

**Separation of Concerns:**
- Core: Configuration, client, model management
- API: Route handlers only
- Conversion: Format translation logic
- Models: Data structures only

**Error Handling:**
- Comprehensive try/catch blocks
- Graceful degradation
- Detailed error messages
- Request cleanup on cancellation

### Provider Configuration Examples

**OpenAI:**
```bash
OPENAI_API_KEY="sk-..."
OPENAI_BASE_URL="https://api.openai.com/v1"
```

**Azure OpenAI:**
```bash
OPENAI_API_KEY="your-azure-key"
OPENAI_BASE_URL="https://your-resource.openai.azure.com/openai/deployments/your-deployment"
AZURE_API_VERSION="2024-02-01"
```

**Ollama (Local):**
```bash
OPENAI_API_KEY="dummy-key"
OPENAI_BASE_URL="http://localhost:11434/v1"
```

**LMP Platform:**
```bash
API_PROVIDER="lmp"
LMP_API_VERSION="V2"
```

## Important Implementation Details

### Request Cancellation
- When client disconnects, the proxy cancels the upstream provider request
- Implemented in `src/core/client.py` using async cancellation tokens
- Prevents resource waste on abandoned requests

### Streaming Support
- Uses Server-Sent Events (SSE) for streaming responses
- Converter in `src/conversion/response_converter.py` handles chunked responses
- Maintains compatibility with Claude's streaming format

### Tool/Function Calling
- Full support for Claude's tool use format
- Converted to OpenAI's function calling format
- Bidirectional conversion of tool results

### Image Support
- Base64 encoded images in messages
- Converted to OpenAI's image URL format
- Supports multimodal inputs

### Custom Headers
- Automatically injected from CUSTOM_HEADER_* environment variables
- Applied to all upstream API requests
- Useful for authentication, tracing, and provider-specific requirements

### Tool Choice Auto-Injection
- Some providers (like bailianLLM) require `tool_choice` field even when optional in OpenAI spec
- When `tools` are present but `tool_choice` is missing, proxy can auto-add it based on `FORCE_TOOL_CHOICE` config
- For providers requiring full object structure (like bailianLLM), automatically generates:
  - Single tool: `tool_choice={type: "function", function: {name: "tool_name"}}`
  - Multiple tools: `tool_choice={type: "function", function: {name: "first_tool_name"}}`
- Set to "none" for strict OpenAI compatibility, or "required" for providers that mandate the field

## Testing with Claude Code

After starting the proxy:

```bash
# If ANTHROPIC_API_KEY is not set in proxy
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="any-value" claude

# If ANTHROPIC_API_KEY is set in proxy (must match)
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="your-key" claude
```

## Recent Changes

- Updated MIDDLE_MODEL config to default to BIG_MODEL value for consistency
