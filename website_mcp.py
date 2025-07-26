try:
    from mcp.server import FastMCP
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Required package 'fastmcp' is missing. Install dependencies with 'pip install -r requirements.txt' before running the server."
    ) from exc
from pydantic import BaseModel, Field
import subprocess, os, json, textwrap, platform, difflib, time
from groq import AsyncGroq
import google.generativeai as genai
from dotenv import load_dotenv
from embedding_manager import EmbeddingManager

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

# Embedding manager for tracking file embeddings
EMBED_MANAGER = EmbeddingManager(SANDBOX)


def check_node_version(min_major: int = 20) -> tuple[bool, str]:
    """Return (True, version) if Node.js meets the required major version."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        ver = result.stdout.strip().lstrip("v")
        major = int(ver.split(".")[0])
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError):
        return False, "Node.js not found"
    return (major >= min_major, f"v{ver}")


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


WRITE_LOG = os.path.join(SANDBOX, "write_log.txt")


@app.tool(name="write_file", description="Create or overwrite a text file")
def write_file(path: PathArg, content: str) -> str:
    full = sandbox_path(path.path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    old = ""
    if os.path.exists(full):
        try:
            with open(full, "r", encoding="utf-8") as fh:
                old = fh.read()
        except OSError:
            old = ""
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    EMBED_MANAGER.update_file(path.path)
    diff = "\n".join(
        difflib.unified_diff(old.splitlines(), content.splitlines(), lineterm="")
    )
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(WRITE_LOG, "a", encoding="utf-8") as log:
            log.write(f"{timestamp} {path.path}\n{diff}\n\n")
    except OSError:
        pass
    summary = "created" if not old else "updated"
    return f"{summary} {path.path}\n{diff[:1000]}"


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


# New tool: return basic OS information
@app.tool(name="get_os", description="Get operating system info")
def get_os() -> str:
    return platform.platform()


# New tool: initialize a React project inside the sandbox
@app.tool(name="init_react_project", description="Create React environment in site-dir")
def init_react_project() -> str:
    ok, ver = check_node_version()
    if not ok:
        return f"Node.js 20+ required. {ver}"
    pkg = os.path.join(SANDBOX, "package.json")
    if os.path.exists(pkg):
        return "React project already initialized"
    try:
        subprocess.run(
            [
                "npm",
                "exec",
                "--yes",
                "create-vite@latest",
                ".",
                "--",
                "--template",
                "react",
            ],
            cwd=SANDBOX,
            check=True,
        )
        subprocess.run(["npm", "install"], cwd=SANDBOX, check=True)
        return "React environment ready"
    except Exception as exc:
        return f"Failed to set up React: {exc}"


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
    {
        "type": "function",
        "function": {
            "name": "get_os",
            "description": "Get operating system info",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "init_react_project",
            "description": "Create React environment in site-dir",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def _run_groq(messages: list[dict], model: str) -> str:
    """Run the conversation using Groq LLM with OpenAI-style tool calling."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY environment variable not set.")
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
                elif call.function.name == "get_os":
                    result = get_os()
                elif call.function.name == "init_react_project":
                    result = init_react_project()
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
            return message.content or ""


async def _run_gemini(messages: list[dict], model: str) -> str:
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
        tools=[
            write_file,
            read_file,
            list_files,
            run_cmd,
            search_docs,
            get_os,
            init_react_project,
        ],
    )

    content = response.candidates[0].content
    text_parts = [p.text for p in content.parts if hasattr(p, "text")]
    return "".join(text_parts)


@app.tool(
    name="compound_tool", description="Agent that uses an LLM to call other tools"
)
async def compound_tool(
    messages: list[dict], model: str = "meta-llama/llama-4-maverick-17b-128e-instruct"
) -> str:
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
