from mcp.server import FastMCP
from pydantic import BaseModel, Field
import subprocess, os, json, textwrap
from groq import AsyncGroq
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from a local .env file so the Groq API key
# can be provided without exporting it globally.
load_dotenv()

# Retrieve API keys from the environment. Only one of them is required.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Gemini / Google API key for using Google's Gemini models
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not GROQ_API_KEY and not GEMINI_API_KEY:
    raise RuntimeError(
        "No API key found. Set GROQ_API_KEY or GEMINI_API_KEY in the environment."
    )
import argparse

SANDBOX = os.path.abspath(os.path.join(os.path.dirname(__file__), "site-dir"))


def sandbox_path(rel: str) -> str:
    """Return an absolute path inside the sandbox or raise ValueError."""
    full = os.path.abspath(os.path.join(SANDBOX, rel))
    if not full.startswith(SANDBOX + os.sep):
        raise ValueError("Path escapes sandbox")
    return full


# FastMCP application instance used to register tools
app = FastMCP()


class PathArg(BaseModel):
    path: str = Field(
        ..., description="Relative path inside site-dir (e.g. 'index.html')"
    )


@app.tool(name="write_file", description="Create or overwrite a text file")
def write_file(path: PathArg, content: str) -> str:
    full = sandbox_path(path.path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"wrote {path.path}"


@app.tool(name="read_file", description="Read a text file")
def read_file(path: PathArg) -> str:
    full = sandbox_path(path.path)
    with open(full, encoding="utf-8") as fh:
        return fh.read()


@app.tool(name="list_files", description="List sandbox dir")
def list_files() -> list[str]:
    out: list[str] = []
    for root, _, files in os.walk(SANDBOX):
        for f in files:
            out.append(os.path.relpath(os.path.join(root, f), SANDBOX))
    return out


class Cmd(BaseModel):
    cmd: str = Field(..., description="Shell cmd run inside ./site-dir")


class SearchQuery(BaseModel):
    query: str = Field(..., description="Terms to search for in ./site-dir/docs")


@app.tool(name="run_cmd", description="Run shell command (e.g. python main.py)")
def run_cmd(arg: Cmd) -> str:
    """Execute a shell command in the sandbox and return its output."""
    try:
        proc = subprocess.run(
            arg.cmd,
            cwd=SANDBOX,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        output = proc.stdout
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "") + "\n<timeout>"
    return output[:4096]


@app.tool(name="search_docs", description="Search guideline docs for text")
def search_docs(arg: SearchQuery) -> str:
    docs_dir = os.path.join(SANDBOX, "docs")
    results = []
    query = arg.query.lower()
    if not os.path.exists(docs_dir):
        return ""
    for root, _, files in os.walk(docs_dir):
        for f in files:
            if not f.lower().endswith((".txt", ".md")):
                continue
            full = os.path.join(root, f)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            if query in text.lower():
                snippet = text[:2000]
                results.append(f"{f}:\n{snippet}")
    return "\n\n".join(results)[:4096]


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a text file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List sandbox dir",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cmd",
            "description": "Run shell command (e.g. python main.py)",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search guideline docs for text",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


async def _run_groq(messages: list[dict], model: str) -> list[str]:
    """Run the conversation using Groq LLM with OpenAI-style tool calling."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY environment variable not set."
        )
    client = AsyncGroq(api_key=GROQ_API_KEY)

    conversation = messages[:]

    while True:
        response = await client.chat.completions.create(
            model=model,
            messages=conversation,
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message
        if message.tool_calls:
            conversation.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [c.model_dump() for c in message.tool_calls],
                }
            )
            for call in message.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                if call.function.name == "write_file":
                    result = write_file(
                        PathArg(path=args.get("path", "")), args.get("content", "")
                    )
                elif call.function.name == "read_file":
                    result = read_file(PathArg(path=args.get("path", "")))
                elif call.function.name == "list_files":
                    result = list_files()
                elif call.function.name == "run_cmd":
                    result = run_cmd(Cmd(cmd=args.get("cmd", "")))
                elif call.function.name == "search_docs":
                    result = search_docs(SearchQuery(query=args.get("query", "")))
                else:
                    result = f"Unknown tool: {call.function.name}"

                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
        else:
            return [message.content] if message.content else []


async def _run_gemini(messages: list[dict], model: str) -> list[str]:
    """Run the conversation using Google's Gemini models with function calls."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set."
        )

    genai.configure(api_key=GEMINI_API_KEY)
    history = [
        {"role": m["role"], "parts": [m.get("content", "")]}
        for m in messages[:-1]
        if m.get("content")
    ]
    chat = genai.GenerativeModel(model).start_chat(
        history=history,
        enable_automatic_function_calling=True,
    )

    last = messages[-1]
    response = await chat.send_message_async(
        last.get("content", ""),
        tools=[write_file, read_file, list_files, run_cmd, search_docs],
    )

    content = response.candidates[0].content
    text_parts = [p.text for p in content.parts if hasattr(p, "text")]
    return ["".join(text_parts)]


@app.tool(
    name="compound_tool", description="Agent that uses an LLM to call other tools"
)
async def compound_tool(
    messages: list[dict], model: str = "meta-llama/llama-4-maverick-17b-128e-instruct"
) -> list[str]:
    """Dispatch to Groq or Gemini depending on the model name."""
    if model.lower().startswith("gemini"):
        return await _run_gemini(messages, model)
    return await _run_groq(messages, model)


def ensure_sandbox() -> None:
    """Create the sandbox directory and git-ignore it if needed."""
    os.makedirs(SANDBOX, exist_ok=True)
    ignore_entry = "site-dir/"
    gitignore = os.path.join(os.getcwd(), ".gitignore")
    lines: list[str] = []
    if os.path.exists(gitignore):
        with open(gitignore, "r", encoding="utf-8") as fh:
            lines = [line.rstrip("\n") for line in fh]
    if ignore_entry not in lines:
        with open(gitignore, "a", encoding="utf-8") as fh:
            if lines and lines[-1] != "":
                fh.write("\n")
            fh.write(f"{ignore_entry}\n")


def main() -> None:
    """CLI entry point for the MCP web builder server."""
    parser = argparse.ArgumentParser(description="Run MCP web builder server")
    parser.add_argument(
        "--model", default="meta-llama/llama-4-maverick-17b-128e-instruct"
    )
    parser.add_argument("--port", type=int, default=4876)
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "sse"],
        default="streamable-http",
        help="Transport to use (default: streamable-http)",
    )
    args = parser.parse_args()

    ensure_sandbox()
    banner = textwrap.dedent(
        f"""
        Running MCP web builder server
        Model : {args.model}
        Port  : {args.port}
        Sandbox: {SANDBOX}
        """
    ).strip()
    print(banner)

    app.settings.port = args.port
    app.run(args.transport)


if __name__ == "__main__":
    main()
