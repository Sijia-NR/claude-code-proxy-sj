"""Test tool choice auto-injection functionality."""

import pytest
import os
from src.conversion.request_converter import convert_claude_to_openai
from src.models.claude import ClaudeMessagesRequest, ClaudeMessage, ClaudeTool
from src.core.model_manager import ModelManager
from src.core.config import config


class TestToolChoiceAutoInjection:
    """Test suite for tool_choice auto-injection feature."""

    def setup_method(self):
        """Setup test fixtures."""
        self.model_manager = ModelManager(config)

    def test_no_tools_no_tool_choice(self):
        """Test that tool_choice is not added when no tools are present."""
        claude_request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            messages=[
                ClaudeMessage(role="user", content="Hello")
            ],
            tools=None,
            tool_choice=None
        )

        result = convert_claude_to_openai(claude_request, self.model_manager)

        # Should not have tool_choice when no tools present
        assert "tool_choice" not in result
        assert "tools" not in result

    def test_tool_choice_auto_injection_single_tool(self):
        """Test that tool_choice is auto-injected when tools present but tool_choice missing (single tool)."""
        # Ensure config is in auto mode
        original_force_mode = config.force_tool_choice
        config.force_tool_choice = "auto"

        try:
            claude_request = ClaudeMessagesRequest(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[
                    ClaudeMessage(role="user", content="查询南京的天气")
                ],
                tools=[
                    ClaudeTool(
                        name="get_weather",
                        description="获取天气信息",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"},
                                "date": {"type": "string"}
                            }
                        }
                    )
                ],
                tool_choice=None
            )

            result = convert_claude_to_openai(claude_request, self.model_manager)

            # Should have tool_choice with full object structure
            assert "tool_choice" in result
            assert result["tool_choice"]["type"] == "function"
            assert result["tool_choice"]["function"]["name"] == "get_weather"
            assert "tools" in result
        finally:
            config.force_tool_choice = original_force_mode

    def test_tool_choice_auto_injection_multiple_tools(self):
        """Test that tool_choice is auto-injected with first tool when multiple tools present."""
        original_force_mode = config.force_tool_choice
        config.force_tool_choice = "auto"

        try:
            claude_request = ClaudeMessagesRequest(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[
                    ClaudeMessage(role="user", content="计算并查询天气")
                ],
                tools=[
                    ClaudeTool(
                        name="calculator",
                        description="计算器",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "expression": {"type": "string"}
                            }
                        }
                    ),
                    ClaudeTool(
                        name="get_weather",
                        description="获取天气信息",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"}
                            }
                        }
                    )
                ],
                tool_choice=None
            )

            result = convert_claude_to_openai(claude_request, self.model_manager)

            # Should have tool_choice with first tool
            assert "tool_choice" in result
            assert result["tool_choice"]["type"] == "function"
            assert result["tool_choice"]["function"]["name"] == "calculator"
            assert len(result["tools"]) == 2
        finally:
            config.force_tool_choice = original_force_mode

    def test_explicit_tool_choice_respected(self):
        """Test that explicitly provided tool_choice is always respected."""
        claude_request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            messages=[
                ClaudeMessage(role="user", content="查询天气")
            ],
            tools=[
                ClaudeTool(
                    name="get_weather",
                    description="获取天气信息",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        }
                    }
                )
            ],
            tool_choice={"type": "any"}
        )

        result = convert_claude_to_openai(claude_request, self.model_manager)

        # Should respect explicit tool_choice
        assert "tool_choice" in result
        assert result["tool_choice"] == "auto"  # "any" is converted to "auto"

    def test_force_tool_choice_none_mode(self):
        """Test that tool_choice is not added when FORCE_TOOL_CHOICE is set to 'none'."""
        original_force_mode = config.force_tool_choice
        config.force_tool_choice = "none"

        try:
            claude_request = ClaudeMessagesRequest(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[
                    ClaudeMessage(role="user", content="查询天气")
                ],
                tools=[
                    ClaudeTool(
                        name="get_weather",
                        description="获取天气信息",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"}
                            }
                        }
                    )
                ],
                tool_choice=None
            )

            result = convert_claude_to_openai(claude_request, self.model_manager)

            # Should NOT add tool_choice in "none" mode
            assert "tool_choice" not in result
            assert "tools" in result
        finally:
            config.force_tool_choice = original_force_mode

    def test_bailian_compatibility(self):
        """Test bailianLLM compatibility: complete tool_choice object structure."""
        original_force_mode = config.force_tool_choice
        config.force_tool_choice = "auto"

        try:
            # Simulate a typical bailianLLM request scenario
            claude_request = ClaudeMessagesRequest(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[
                    ClaudeMessage(role="user", content="南京今天天气怎么样？")
                ],
                tools=[
                    ClaudeTool(
                        name="get_weather",
                        description="获取指定地点的天气信息",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "城市名称"
                                },
                                "date": {
                                    "type": "string",
                                    "description": "日期 (可选)"
                                }
                            },
                            "required": ["location"]
                        }
                    )
                ],
                tool_choice=None
            )

            result = convert_claude_to_openai(claude_request, self.model_manager)

            # Verify bailianLLM requirements: complete tool_choice object
            assert "tool_choice" in result, "tool_choice must be present for bailianLLM"
            assert isinstance(result["tool_choice"], dict), "tool_choice must be an object, not a string"
            assert "type" in result["tool_choice"], "tool_choice must have 'type' field"
            assert result["tool_choice"]["type"] == "function", "type must be 'function'"
            assert "function" in result["tool_choice"], "tool_choice must have 'function' field"
            assert "name" in result["tool_choice"]["function"], "function must have 'name' field"
            assert result["tool_choice"]["function"]["name"] == "get_weather", "name must match tool name"

            # Verify tools are present
            assert "tools" in result
            assert len(result["tools"]) == 1
            assert result["tools"][0]["type"] == "function"
        finally:
            config.force_tool_choice = original_force_mode

    def test_default_tool_choice_custom_name(self):
        """Test that DEFAULT_TOOL_CHOICE can specify a custom tool name."""
        original_force_mode = config.force_tool_choice
        original_default_choice = config.default_tool_choice
        config.force_tool_choice = "auto"
        config.default_tool_choice = "get_weather"

        try:
            claude_request = ClaudeMessagesRequest(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[
                    ClaudeMessage(role="user", content="查询天气")
                ],
                tools=[
                    ClaudeTool(
                        name="calculator",
                        description="计算器",
                        input_schema={"type": "object", "properties": {}}
                    ),
                    ClaudeTool(
                        name="get_weather",
                        description="获取天气",
                        input_schema={"type": "object", "properties": {}}
                    )
                ],
                tool_choice=None
            )

            result = convert_claude_to_openai(claude_request, self.model_manager)

            # Should use the configured default tool name
            assert "tool_choice" in result
            assert result["tool_choice"]["function"]["name"] == "get_weather"
        finally:
            config.force_tool_choice = original_force_mode
            config.default_tool_choice = original_default_choice

    def test_empty_tools_array(self):
        """Test that tool_choice is not added when tools array is empty."""
        original_force_mode = config.force_tool_choice
        config.force_tool_choice = "auto"

        try:
            claude_request = ClaudeMessagesRequest(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[
                    ClaudeMessage(role="user", content="Hello")
                ],
                tools=[],
                tool_choice=None
            )

            result = convert_claude_to_openai(claude_request, self.model_manager)

            # Should not add tool_choice for empty tools array
            assert "tool_choice" not in result
        finally:
            config.force_tool_choice = original_force_mode
