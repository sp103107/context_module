"""Example: Using the LLM Adapter for hybrid local/cloud LLM support.

This demonstrates how to use the LLMClient with different providers.
"""

from aos_context.config import LLMConfig
from aos_context.llm_adapter import LLMClient, create_llm_client


def example_openai():
    """Example: Using OpenAI (cloud)."""
    print("=== OpenAI Example ===")
    
    # Option 1: From environment variables
    # Set: export OPENAI_API_KEY=sk-...
    # Set: export LLM_PROVIDER=openai
    # Set: export LLM_MODEL_NAME=gpt-4o
    client = create_llm_client()
    
    # Option 2: Explicit configuration
    config = LLMConfig(
        provider="openai",
        model_name="gpt-4o",
        api_key="sk-...",  # Or use OPENAI_API_KEY env var
    )
    client = LLMClient(config)
    
    messages = [
        {"role": "user", "content": "What is 2+2?"}
    ]
    
    try:
        response = client.complete(messages)
        print(f"Response: {response}")
    except ImportError as e:
        print(f"Error: {e}")
        print("Install OpenAI client: pip install openai")


def example_ollama():
    """Example: Using Ollama (local)."""
    print("\n=== Ollama Example ===")
    
    config = LLMConfig(
        provider="ollama",
        base_url="http://localhost:11434/v1",  # Ollama default
        model_name="llama3",
    )
    client = LLMClient(config)
    
    messages = [
        {"role": "user", "content": "What is 2+2?"}
    ]
    
    try:
        response = client.complete(messages)
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure Ollama is running: ollama serve")


def example_lm_studio():
    """Example: Using LM Studio (local OpenAI-compatible server)."""
    print("\n=== LM Studio Example ===")
    
    config = LLMConfig(
        provider="local",
        base_url="http://localhost:1234/v1",  # LM Studio default
        model_name="llama-3-8b-instruct",
    )
    client = LLMClient(config)
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ]
    
    try:
        response = client.complete(messages, temperature=0.8)
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure LM Studio server is running on port 1234")


def example_anthropic():
    """Example: Using Anthropic Claude (cloud)."""
    print("\n=== Anthropic Example ===")
    
    # Option 1: From environment
    # Set: export ANTHROPIC_API_KEY=sk-ant-...
    # Set: export LLM_PROVIDER=anthropic
    # Set: export LLM_MODEL_NAME=claude-3-5-sonnet-20241022
    config = LLMConfig.from_env()
    config = LLMConfig(
        provider=config.provider or "anthropic",
        model_name=config.model_name or "claude-3-5-sonnet-20241022",
        api_key=config.api_key,  # From ANTHROPIC_API_KEY env var
    )
    client = LLMClient(config)
    
    messages = [
        {"role": "user", "content": "What is 2+2?"}
    ]
    
    try:
        response = client.complete(messages)
        print(f"Response: {response}")
    except ImportError as e:
        print(f"Error: {e}")
        print("Install Anthropic client: pip install anthropic")


def example_environment_variables():
    """Example: Configuration via environment variables."""
    print("\n=== Environment Variables Example ===")
    print("""
Set these environment variables:

# For OpenAI
export LLM_PROVIDER=openai
export LLM_MODEL_NAME=gpt-4o
export OPENAI_API_KEY=sk-...

# For Anthropic
export LLM_PROVIDER=anthropic
export LLM_MODEL_NAME=claude-3-5-sonnet-20241022
export ANTHROPIC_API_KEY=sk-ant-...

# For Ollama (local)
export LLM_PROVIDER=ollama
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_MODEL_NAME=llama3

# For LM Studio (local)
export LLM_PROVIDER=local
export LLM_BASE_URL=http://localhost:1234/v1
export LLM_MODEL_NAME=llama-3-8b-instruct

Then use:
    from aos_context.llm_adapter import create_llm_client
    client = create_llm_client()
    response = client.complete([{"role": "user", "content": "Hello"}])
    """)


if __name__ == "__main__":
    print("LLM Adapter Usage Examples\n")
    print("=" * 60)
    
    # Show environment variable example
    example_environment_variables()
    
    # Uncomment to test actual providers (requires API keys/servers)
    # example_openai()
    # example_ollama()
    # example_lm_studio()
    # example_anthropic()

