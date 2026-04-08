"""
Simple Strands Agent with DuckDuckGo, Context7 MCP, and Braintrust Observability.

This agent demonstrates:
- DuckDuckGo web search tool
- Context7 MCP server for documentation search
- Braintrust observability using OpenTelemetry
- Anthropic Claude Haiku via Strands
"""

import asyncio
import json
import logging
import os
from typing import Optional

from braintrust.otel import BraintrustSpanProcessor
from ddgs import DDGS
from dotenv import load_dotenv
from mcp.client.streamable_http import streamablehttp_client
from opentelemetry.sdk.trace import TracerProvider
from strands import Agent
from strands.telemetry import StrandsTelemetry
from strands.tools.decorator import tool
from strands.tools.mcp import MCPClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()


def _get_env_var(
    key: str,
    default: Optional[str] = None
) -> str:
    """Get environment variable or raise error if not found."""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} not set")
    return value


@tool
def duckduckgo_search(
    query: str,
    max_results: int = 5
) -> str:
    """
    Search DuckDuckGo for the given query. Use this for current events, news, general information, or any topic that requires web search.

    Args:
        query: The search query string
        max_results: Maximum number of results to return

    Returns:
        JSON string containing search results
    """
    try:
        logger.info(f"Searching DuckDuckGo for: {query}")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        logger.info(f"Found {len(results)} results")
        return json.dumps(results, indent=2)

    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return json.dumps({"error": str(e)})


def _setup_observability() -> TracerProvider:
    """
    Set up OpenTelemetry with Braintrust for observability.

    Returns:
        Configured TracerProvider instance
    """
    logger.info("Setting up Braintrust observability")

    # Get Braintrust configuration
    braintrust_api_key = _get_env_var("BRAINTRUST_API_KEY")
    braintrust_project = _get_env_var("BRAINTRUST_PROJECT")

    # Create TracerProvider and add Braintrust processor
    # Pass api_key and parent directly to BraintrustSpanProcessor
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        BraintrustSpanProcessor(
            api_key=braintrust_api_key,
            parent=braintrust_project
        )
    )

    # Set tracer provider as global
    from opentelemetry import trace
    trace.set_tracer_provider(tracer_provider)

    logger.info(f"Braintrust observability configured for project: {braintrust_project}")
    return tracer_provider


def _create_context7_transport():
    return streamablehttp_client("https://mcp.context7.com/mcp")


def _build_agent(mcp_tools: list) -> Agent:
    """
    Build the Strands agent given a list of MCP tools.
    Must be called while the MCPClient context manager is still active.

    Args:
        mcp_tools: Tools loaded from the Context7 MCP server

    Returns:
        Configured Agent instance
    """
    logger.info("Creating Strands agent")

    # Set up observability
    tracer_provider = _setup_observability()
    telemetry = StrandsTelemetry(tracer_provider=tracer_provider)

    # Get API key and set it in environment for LiteLLM
    anthropic_api_key = _get_env_var("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key

    system_prompt = """You are a helpful AI assistant with access to DuckDuckGo web search and Context7 documentation search.

Use the DuckDuckGo search tool for current events, news, and general information.
Use the Context7 MCP tools (resolve-library-id and get-library-docs) to look up official documentation for programming libraries and frameworks.
Provide clear, accurate, and helpful responses based on search results and documentation.
Always cite your sources when using search results or documentation."""

    from strands.models import AnthropicModel

    model = AnthropicModel(
        model_id="claude-3-haiku-20240307",
        max_tokens=4096
    )

    agent = Agent(
        system_prompt=system_prompt,
        model=model,
        tools=[duckduckgo_search] + mcp_tools
    )

    logger.info(f"Agent created with DuckDuckGo + {len(mcp_tools)} Context7 MCP tools")
    return agent


async def _run_agent_async(
    agent: Agent,
    user_input: str
) -> str:
    """
    Run the agent asynchronously with the given input.

    Args:
        agent: The Strands agent instance
        user_input: User's question or prompt

    Returns:
        Agent's response
    """
    logger.info(f"Processing user input: {user_input}")

    response = await agent.invoke_async(user_input)

    logger.info("Agent response generated")
    return response


def main() -> None:
    """Main function to run the agent."""
    logger.info("Starting Simple Agent with Observability")

    print("\n" + "="*80)
    print("Simple Agent with Observability Demo")
    print("="*80 + "\n")

    # Keep the MCP client context alive for the entire interactive session
    # so MCP tool calls remain valid while the agent is running
    mcp_client = MCPClient(_create_context7_transport)
    with mcp_client:
        mcp_tools = mcp_client.list_tools_sync()
        logger.info(f"Loaded {len(mcp_tools)} tools from Context7 MCP server")

        agent = _build_agent(mcp_tools)

        print("Ask me anything! I can search the web with DuckDuckGo and look up docs via Context7.")
        print("Type 'quit' to exit.\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue

                response = asyncio.run(_run_agent_async(agent, user_input))

                print(f"\nAgent: {response}\n")

            except EOFError:
                print("\n\nGoodbye!")
                break
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                logger.error(f"Error running agent: {e}")
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
