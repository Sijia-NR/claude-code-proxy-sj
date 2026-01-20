import asyncio
import json
from fastapi import HTTPException
from typing import Optional, AsyncGenerator, Dict, Any
import httpx
from openai import AsyncOpenAI, AsyncAzureOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai._exceptions import APIError, RateLimitError, AuthenticationError, BadRequestError

class OpenAIClient:
    """Async OpenAI client with cancellation support."""
    
    def __init__(self, api_key: str, base_url: str, timeout: int = 90, api_version: Optional[str] = None, custom_headers: Optional[Dict[str, str]] = None, api_provider: str = "openai", lmp_api_version: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.custom_headers = custom_headers or {}
        self.api_provider = api_provider
        self.lmp_api_version = lmp_api_version
        self.client = None  # Will be set to None for LMP mode
        self.active_requests: Dict[str, asyncio.Event] = {}

        # Only create OpenAI client if NOT in LMP mode
        if api_provider != "lmp":
            # Prepare default headers
            default_headers = {
                "Content-Type": "application/json",
                "User-Agent": "claude-proxy/1.0.0"
            }

            # Merge custom headers with default headers
            all_headers = {**default_headers, **self.custom_headers}

            # Detect if using Azure and instantiate the appropriate client
            if api_version:
                self.client = AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=base_url,
                    api_version=api_version,
                    timeout=timeout,
                    default_headers=all_headers
                )
            else:
                self.client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=timeout,
                    default_headers=all_headers
                )

    def _get_lmp_endpoint(self) -> str:
        """Get the LMP endpoint path based on API version."""
        base_path = "/lmp-cloud-ias-server/api/llm/chat/completions"
        if self.lmp_api_version == "V2":
            return f"{base_path}/V2"
        return base_path
    
    async def create_chat_completion(self, request: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """Send chat completion to OpenAI API with cancellation support."""

        # For LMP mode, use direct HTTP request
        if self.api_provider == "lmp":
            return await self._lmp_chat_completion(request, request_id)

        # Create cancellation token if request_id provided
        if request_id:
            cancel_event = asyncio.Event()
            self.active_requests[request_id] = cancel_event

        try:
            # Create task that can be cancelled
            completion_task = asyncio.create_task(
                self.client.chat.completions.create(**request)
            )

            if request_id:
                # Wait for either completion or cancellation
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, pending = await asyncio.wait(
                    [completion_task, cancel_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if request was cancelled
                if cancel_task in done:
                    completion_task.cancel()
                    raise HTTPException(status_code=499, detail="Request cancelled by client")

                completion = await completion_task
            else:
                completion = await completion_task

            # Convert to dict format that matches the original interface
            return completion.model_dump()

        except AuthenticationError as e:
            raise HTTPException(status_code=401, detail=self.classify_openai_error(str(e)))
        except RateLimitError as e:
            raise HTTPException(status_code=429, detail=self.classify_openai_error(str(e)))
        except BadRequestError as e:
            raise HTTPException(status_code=400, detail=self.classify_openai_error(str(e)))
        except APIError as e:
            status_code = getattr(e, 'status_code', 500)
            raise HTTPException(status_code=status_code, detail=self.classify_openai_error(str(e)))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

        finally:
            # Clean up active request tracking
            if request_id and request_id in self.active_requests:
                del self.active_requests[request_id]

    async def _lmp_chat_completion(self, request: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """Send LMP chat completion using direct HTTP request."""
        # Build LMP endpoint URL
        lmp_path = "/lmp-cloud-ias-server/api/llm/chat/completions"
        if self.lmp_api_version == "V2":
            lmp_path = f"{lmp_path}/V2"
        url = f"{self.base_url.rstrip('/')}{lmp_path}"

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,  # LMP uses APP_KEY directly
            **self.custom_headers
        }

        # Create cancellation token if request_id provided
        if request_id:
            cancel_event = asyncio.Event()
            self.active_requests[request_id] = cancel_event

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                if request_id:
                    # Wait for either completion or cancellation
                    async def make_request():
                        response = await client.post(url, json=request, headers=headers)
                        return response

                    request_task = asyncio.create_task(make_request())
                    cancel_task = asyncio.create_task(cancel_event.wait())

                    done, pending = await asyncio.wait(
                        [request_task, cancel_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    if cancel_task in done:
                        request_task.cancel()
                        raise HTTPException(status_code=499, detail="Request cancelled by client")

                    response = await request_task
                else:
                    response = await client.post(url, json=request, headers=headers)

                if response.status_code != 200:
                    try:
                        error_data = response.json()
                    except:
                        error_data = {}
                    # Check for LMP error format
                    if "code" in error_data or isinstance(error_data, dict):
                        raise HTTPException(status_code=response.status_code, detail=error_data)
                    raise HTTPException(status_code=response.status_code, detail=response.text)

                return response.json()

        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=self.classify_openai_error(e.response.text))
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        finally:
            if request_id and request_id in self.active_requests:
                del self.active_requests[request_id]
    
    async def create_chat_completion_stream(self, request: Dict[str, Any], request_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Send streaming chat completion to OpenAI API with cancellation support."""

        # For LMP mode, use direct HTTP request
        if self.api_provider == "lmp":
            async for chunk in self._lmp_chat_completion_stream(request, request_id):
                yield chunk
            return

        # Create cancellation token if request_id provided
        if request_id:
            cancel_event = asyncio.Event()
            self.active_requests[request_id] = cancel_event

        try:
            # Ensure stream is enabled
            request["stream"] = True
            if "stream_options" not in request:
                request["stream_options"] = {}
            request["stream_options"]["include_usage"] = True

            # Create the streaming completion
            streaming_completion = await self.client.chat.completions.create(**request)

            async for chunk in streaming_completion:
                # Check for cancellation before yielding each chunk
                if request_id and request_id in self.active_requests:
                    if self.active_requests[request_id].is_set():
                        raise HTTPException(status_code=499, detail="Request cancelled by client")

                # Convert chunk to SSE format
                chunk_dict = chunk.model_dump()
                chunk_json = json.dumps(chunk_dict, ensure_ascii=False)
                yield f"data: {chunk_json}"

            # Signal end of stream
            yield "data: [DONE]"

        except AuthenticationError as e:
            raise HTTPException(status_code=401, detail=self.classify_openai_error(str(e)))
        except RateLimitError as e:
            raise HTTPException(status_code=429, detail=self.classify_openai_error(str(e)))
        except BadRequestError as e:
            raise HTTPException(status_code=400, detail=self.classify_openai_error(str(e)))
        except APIError as e:
            status_code = getattr(e, 'status_code', 500)
            raise HTTPException(status_code=status_code, detail=self.classify_openai_error(str(e)))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

        finally:
            # Clean up active request tracking
            if request_id and request_id in self.active_requests:
                del self.active_requests[request_id]

    async def _lmp_chat_completion_stream(self, request: Dict[str, Any], request_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Send LMP streaming chat completion using direct HTTP request."""
        # Build LMP endpoint URL
        lmp_path = "/lmp-cloud-ias-server/api/llm/chat/completions"
        if self.lmp_api_version == "V2":
            lmp_path = f"{lmp_path}/V2"
        url = f"{self.base_url.rstrip('/')}{lmp_path}"

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            **self.custom_headers
        }

        # Ensure stream is enabled
        request["stream"] = True

        # Create cancellation token if request_id provided
        if request_id:
            cancel_event = asyncio.Event()
            self.active_requests[request_id] = cancel_event

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async def make_request():
                    return client.stream("POST", url, json=request, headers=headers)

                if request_id:
                    request_task = asyncio.create_task(make_request())
                    cancel_task = asyncio.create_task(cancel_event.wait())

                    done, pending = await asyncio.wait(
                        [request_task, cancel_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    if cancel_task in done:
                        request_task.cancel()
                        raise HTTPException(status_code=499, detail="Request cancelled by client")

                    response = await request_task
                else:
                    response = await make_request()

                if response.status_code != 200:
                    content = await response.aread()
                    raise HTTPException(status_code=response.status_code, detail=content.decode())

                # Process streaming response
                is_v2 = self.lmp_api_version == "V2"
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    # Check for cancellation
                    if request_id and request_id in self.active_requests:
                        if self.active_requests[request_id].is_set():
                            raise HTTPException(status_code=499, detail="Request cancelled by client")

                    # V2 format: no "data:" prefix, just raw JSON
                    # V1 format: standard SSE with "data:" prefix
                    if is_v2:
                        yield line
                    else:
                        # For V1, ensure data: prefix exists
                        if line.startswith("data:"):
                            yield line
                        else:
                            yield f"data: {line}"

                # Signal end of stream
                if is_v2:
                    yield "[DONE]"
                else:
                    yield "data: [DONE]"

        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=self.classify_openai_error(e.response.text))
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        finally:
            if request_id and request_id in self.active_requests:
                del self.active_requests[request_id]

    def classify_openai_error(self, error_detail: Any) -> str:
        """Provide specific error guidance for common OpenAI API issues."""
        error_str = str(error_detail).lower()

        # LMP error codes
        if self.api_provider == "lmp":
            # Check for LMP error code patterns
            if "300001" in error_str or "鉴权失败" in error_str:
                return "Authentication failed. Please check your API key configuration."
            if "300002" in error_str or "权限被拒绝" in error_str:
                return "Permission denied. Your API key does not have access to this resource."
            if any(code in error_str for code in ["200001", "200002", "200003", "200004", "200005"]):
                return "Invalid request parameters. Please check your request format."
            if "400001" in error_str or "400002" in error_str:
                return "Server error. Please try again later."

        # Region/country restrictions
        if "unsupported_country_region_territory" in error_str or "country, region, or territory not supported" in error_str:
            return "OpenAI API is not available in your region. Consider using a VPN or Azure OpenAI service."

        # API key issues
        if "invalid_api_key" in error_str or "unauthorized" in error_str:
            return "Invalid API key. Please check your OPENAI_API_KEY configuration."

        # Rate limiting
        if "rate_limit" in error_str or "quota" in error_str:
            return "Rate limit exceeded. Please wait and try again, or upgrade your API plan."

        # Model not found
        if "model" in error_str and ("not found" in error_str or "does not exist" in error_str):
            return "Model not found. Please check your BIG_MODEL and SMALL_MODEL configuration."

        # Billing issues
        if "billing" in error_str or "payment" in error_str:
            return "Billing issue. Please check your OpenAI account billing status."

        # Default: return original message
        return str(error_detail)
    
    def cancel_request(self, request_id: str) -> bool:
        """Cancel an active request by request_id."""
        if request_id in self.active_requests:
            self.active_requests[request_id].set()
            return True
        return False