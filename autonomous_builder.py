import os
import argparse
import platform
import subprocess
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

# Variant for React projects
SYSTEM_PROMPT_REACT = (
    "You are an expert React developer. First call get_os to check the system, "
    "then call init_react_project once to set up the environment. Use write_file "
    "for JSX components under site-dir/src and run npm scripts with run_cmd when "
    "needed."
)


SPEC_PATH = os.path.join('docs', 'spec.md')
SITE_TYPES = ['html', 'react']


def ensure_react_env() -> None:
    """Initialize a React project in site-dir if missing."""
    pkg = os.path.join('site-dir', 'package.json')
    if os.path.exists(pkg):
        return
    try:
        subprocess.run(
            ['npm', 'create', 'vite@latest', '.', '--', '--template', 'react'],
            cwd='site-dir',
            check=True,
        )
        subprocess.run(['npm', 'install'], cwd='site-dir', check=True)
    except Exception:
        print('Warning: unable to set up React environment. Ensure Node.js is installed.')

async def auto_build(iterations: int, model: str, site_type: str) -> None:
    """Run compound_tool repeatedly to incrementally build the site."""
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if not os.path.exists(SPEC_PATH):
        raise FileNotFoundError(f"Spec file not found: {SPEC_PATH}")
    with open(SPEC_PATH, 'r', encoding='utf-8') as fh:
        spec = fh.read()

    system = SYSTEM_PROMPT_REACT if site_type == "react" else SYSTEM_PROMPT
    if site_type == "react":
        print("OS:", platform.platform())
        ensure_react_env()
    messages = [
        {"role": "system", "content": system},
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
    if site_type == "react":
        try:
            subprocess.run(["npm", "run", "build"], cwd="site-dir", check=True)
        except Exception as exc:
            print("React build failed:", exc)
        else:
            print("React build completed. Run 'npm run dev' inside site-dir to preview.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomously build the site")
    parser.add_argument("--iterations", type=int, default=3, help="Number of build steps to perform")
    parser.add_argument("--model", default="meta-llama/llama-4-maverick-17b-128e-instruct")
    parser.add_argument("--type", choices=SITE_TYPES, default="html", help="Project type: html or react")
    args = parser.parse_args()
    anyio.run(auto_build, args.iterations, args.model, args.type)
