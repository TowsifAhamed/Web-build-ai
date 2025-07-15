import os
import argparse
import anyio
from website_mcp import compound_tool

SPEC_PATH = os.path.join('docs', 'spec.md')

async def auto_build(iterations: int, model: str) -> None:
    """Run compound_tool repeatedly to incrementally build the site."""
    if not os.path.exists(SPEC_PATH):
        raise FileNotFoundError(f"Spec file not found: {SPEC_PATH}")
    with open(SPEC_PATH, 'r', encoding='utf-8') as fh:
        spec = fh.read()

    messages = [{"role": "user", "content": spec}]
    for _ in range(iterations):
        result = await compound_tool(messages, model=model)
        if result:
            messages.append({"role": "assistant", "content": result[0]})
        else:
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomously build the site")
    parser.add_argument("--iterations", type=int, default=3, help="Number of build steps to perform")
    parser.add_argument("--model", default="meta-llama/llama-4-maverick-17b-128e-instruct")
    args = parser.parse_args()
    anyio.run(auto_build, args.iterations, args.model)
