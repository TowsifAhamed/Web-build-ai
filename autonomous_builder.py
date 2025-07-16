import os
import argparse
import anyio
from website_mcp import compound_tool

# Prompt given to the LLM before any build steps. It explains how to use the
# available tools to generate or update files inside the sandbox. This helps
# ensure the model actually writes HTML/CSS rather than only describing it.
SYSTEM_PROMPT = (
    "You are an expert web developer. Use write_file to create or overwrite "
    "files when building the site. Provide paths relative to the site-dir "
    "sandbox such as 'index.html' or 'css/style.css' \u2013 do not prefix them "
    "with 'site-dir/'. Replace existing files when refining the project."
)


SPEC_PATH = os.path.join('docs', 'spec.md')

async def auto_build(iterations: int, model: str) -> None:
    """Run compound_tool repeatedly to incrementally build the site."""
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if not os.path.exists(SPEC_PATH):
        raise FileNotFoundError(f"Spec file not found: {SPEC_PATH}")
    with open(SPEC_PATH, 'r', encoding='utf-8') as fh:
        spec = fh.read()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": spec},
    ]
    for step in range(iterations):
        if step > 0:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Please refine the website. Replace any older files with improved versions and add new code as needed."
                    ),
                }
            )
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
