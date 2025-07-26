import os
import sys
import subprocess
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import shutil
import re
import anyio
import webbrowser
from dotenv import load_dotenv
from mcp.client.session_group import ClientSessionGroup, SseServerParameters

MCP_PORT = 4876
MCP_URL = f"http://localhost:{MCP_PORT}/sse"
UPLOAD_DIR = os.path.join("site-dir", "uploads")
DOCS_DIR = os.path.join("site-dir", "docs")
DEV_SERVER_PORT = 5173
vite_process: subprocess.Popen | None = None


def ensure_nodejs(min_major: int = 20) -> bool:
    """Install Node.js via nvm if missing and return True if available."""
    if check_node_version(min_major):
        return True
    try:
        # Install nvm if it's not already present
        if subprocess.run("command -v nvm", shell=True).returncode != 0:
            subprocess.run(
                "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash",
                shell=True,
                check=True,
            )
        # Install and activate the required Node version
        subprocess.run(
            [
                "bash",
                "-c",
                f"source $HOME/.nvm/nvm.sh && nvm install {min_major} && nvm use {min_major}",
            ],
            check=True,
        )
        # Update PATH for the current process
        node_bin = (
            subprocess.check_output(
                [
                    "bash",
                    "-c",
                    f"source $HOME/.nvm/nvm.sh && nvm which {min_major}",
                ]
            )
            .decode()
            .strip()
        )
        os.environ["PATH"] = (
            os.path.dirname(node_bin) + os.pathsep + os.environ.get("PATH", "")
        )
    except Exception:
        return False
    return check_node_version(min_major)


def check_node_version(min_major: int = 20) -> bool:
    """Return True if the installed Node.js meets the required major version."""
    try:
        out = subprocess.run(
            ["node", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        ver = out.stdout.strip().lstrip("v")
        major = int(ver.split(".")[0])
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError):
        return False
    return major >= min_major


# System prompt explaining how to use the available tools. This is inserted
# once at the start of a conversation so the model knows to create or update
# files in the sandbox using write_file.
SYSTEM_PROMPT = (
    "You are an expert web developer. Use write_file to create or replace HTML, "
    "CSS and JS files. Provide paths relative to the site-dir sandbox, for "
    "example 'index.html' or 'scripts/app.js'. Do not prefix paths with 'site-dir/'. Overwrite existing files when refining the site."
)

# Extended prompt for React projects
SYSTEM_PROMPT_REACT = (
    "You are an expert React developer. Call get_os to check the system then "
    "init_react_project to set up the environment. Use write_file for JSX "
    "components in site-dir/src and run npm scripts with run_cmd when needed."
)

# Load environment variables from a .env file if present so the UI and
# MCP server both have access to API keys without requiring them to be
# exported globally.
load_dotenv()

# Lists of available models sorted by release date (latest first). Only Groq
# and Gemini models are included here.
GROQ_MODEL_OPTIONS = [
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen-qwq-32b",
    "mistral-saba-24b",
    "gemma2-9b-it",
    "deepseek-ai/deepseek-v2-chat",
    "llama-3.3-70b-specdec",
    "llama-3.3-70b-versatile",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "llama-guard-3-8b",
    "deepseek-r1-distill-llama-70b",
]

GEMINI_MODEL_OPTIONS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-8b",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

DEFAULT_MODEL_ENV = os.getenv("MCP_MODEL")
current_model = ""
MODEL_OPTIONS: list[str] = []
SPEC_FILE = os.path.join("docs", "spec.md")

# Supported project types
SITE_TYPES = ["html", "react"]
current_site_type = "html"

# conversation history for revision prompts
conversation: list[dict] = []


async def call_compound_tool(prompt: str, site_type: str) -> str:
    """Send the next user prompt using the conversation history."""
    if not conversation:
        system = SYSTEM_PROMPT_REACT if site_type == "react" else SYSTEM_PROMPT
        conversation.append({"role": "system", "content": system})
    conversation.append({"role": "user", "content": prompt})
    if len(conversation) > 2:
        conversation.append(
            {
                "role": "user",
                "content": "Please improve the site. Replace outdated files with enhanced versions and add new code where useful.",
            }
        )
    async with ClientSessionGroup() as group:
        session = await group.connect_to_server(SseServerParameters(url=MCP_URL))
        result = await session.call_tool(
            "compound_tool", {"messages": conversation, "model": current_model}
        )
        text_blocks = [b.text for b in result.content if hasattr(b, "text")]
        text = "".join(text_blocks) if text_blocks else ""
        conversation.append({"role": "assistant", "content": text})
        return text


async def auto_build(prompt: str, iterations: int, site_type: str) -> None:
    """Run multiple build steps automatically using the MCP server."""
    if iterations < 1:
        raise ValueError("Build steps must be at least 1")
    if not conversation:
        system = SYSTEM_PROMPT_REACT if site_type == "react" else SYSTEM_PROMPT
        conversation.append({"role": "system", "content": system})
    conversation.append({"role": "user", "content": prompt})
    async with ClientSessionGroup() as group:
        session = await group.connect_to_server(SseServerParameters(url=MCP_URL))
        for step in range(iterations):
            if step > 0:
                conversation.append(
                    {
                        "role": "user",
                        "content": "Please improve the site by updating existing files with better code and adding new sections if helpful.",
                    }
                )
            result = await session.call_tool(
                "compound_tool", {"messages": conversation, "model": current_model}
            )
            text_blocks = [b.text for b in result.content if hasattr(b, "text")]
            text = "".join(text_blocks) if text_blocks else ""
            conversation.append({"role": "assistant", "content": text})


def parse_spec_file():
    """Read docs/spec.md and return parsed fields."""
    if not os.path.exists(SPEC_FILE):
        raise FileNotFoundError(SPEC_FILE)
    with open(SPEC_FILE, "r", encoding="utf-8") as fh:
        text = fh.read()
    name = ""
    style = ""
    colors = ""
    desc = text
    extra = ""
    m = re.search(r"Business name:\s*(.+)", text)
    if m:
        name = m.group(1).strip()
    m = re.search(r"Proposed tagline:\s*(.+)", text)
    tagline = m.group(1).strip() if m else ""
    m = re.search(r"Overall vibe:\s*(.+)", text)
    if m:
        style = m.group(1).strip()
    m = re.search(
        r"Color scheme:(.*?)(?:\nFollow|\nAdditional|\nAccessibility|\nPerformance|$)",
        text,
        re.S,
    )
    if m:
        colors = " ".join(
            line.strip() for line in m.group(1).splitlines() if line.strip()
        )
    m = re.search(
        r"Structure & key pages(.*?)(?:\nResponsive grid|\nDesign style:|$)", text, re.S
    )
    if m:
        desc = m.group(1).strip()
    if tagline:
        desc = f"Proposed tagline: {tagline}\n\n" + desc
    m = re.search(r"Additional instructions:(.*)", text, re.S)
    if m:
        extra = m.group(1).strip()
    return name, style, colors, desc, extra


def ensure_react_env() -> None:
    """Create a basic React project inside site-dir if missing."""
    if not ensure_nodejs():
        messagebox.showwarning(
            "Node.js required",
            "Node.js 20 or newer is required to run the React dev server.",
        )
        return
    pkg_json = os.path.join("site-dir", "package.json")
    if os.path.exists(pkg_json):
        return
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
            cwd="site-dir",
            check=True,
        )
        subprocess.run(["npm", "install"], cwd="site-dir", check=True)
    except Exception:
        messagebox.showwarning(
            "React setup failed",
            "Could not initialize React environment. Ensure Node.js and npm are installed.",
        )


def start_vite_server() -> None:
    """Launch the Vite development server if it's not already running."""
    global vite_process
    if vite_process and vite_process.poll() is None:
        return
    if not ensure_nodejs():
        messagebox.showwarning(
            "Node.js required",
            "Node.js 20 or newer is required to run the React dev server.",
        )
        return
    try:
        vite_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="site-dir",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception:
        messagebox.showwarning(
            "Vite failed",
            "Could not start the React development server. Ensure Node.js and npm are installed.",
        )


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "website_mcp.py",
            "--port",
            str(MCP_PORT),
            "--transport",
            "sse",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main():
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    global MODEL_OPTIONS, current_model
    MODEL_OPTIONS = []
    if groq_key:
        MODEL_OPTIONS.extend(GROQ_MODEL_OPTIONS)
    if gemini_key:
        MODEL_OPTIONS.extend(GEMINI_MODEL_OPTIONS)

    if not MODEL_OPTIONS:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "API key required",
            "Please set GROQ_API_KEY or GEMINI_API_KEY in the environment.",
        )
        return

    default_model = DEFAULT_MODEL_ENV or MODEL_OPTIONS[0]
    current_model = default_model

    server = start_server()
    root = tk.Tk()
    root.title("Website Builder")
    root.geometry("1000x700")

    pane = tk.PanedWindow(root, orient=tk.HORIZONTAL)
    pane.pack(fill="both", expand=True)

    left_container = tk.Frame(pane)
    left_canvas = tk.Canvas(left_container)
    yscroll = tk.Scrollbar(left_container, orient="vertical", command=left_canvas.yview)
    scroll_frame = tk.Frame(left_canvas)
    scroll_frame.bind(
        "<Configure>",
        lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")),
    )
    left_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    left_canvas.configure(yscrollcommand=yscroll.set)
    left_canvas.pack(side="left", fill="both", expand=True)
    yscroll.pack(side="right", fill="y")

    right_frame = tk.Frame(pane)

    pane.add(left_container, stretch="always")
    pane.add(right_frame, stretch="always")

    tk.Label(scroll_frame, text="Business name:").pack(anchor="w")
    name_entry = tk.Entry(scroll_frame, width=60)
    name_entry.pack(fill="x")

    tk.Label(scroll_frame, text="Design style:").pack(anchor="w")
    style_entry = tk.Entry(scroll_frame, width=60)
    style_entry.pack(fill="x")

    tk.Label(scroll_frame, text="Color scheme:").pack(anchor="w")
    color_entry = tk.Entry(scroll_frame, width=60)
    color_entry.pack(fill="x")

    tk.Label(scroll_frame, text="Model:").pack(anchor="w")
    model_var = tk.StringVar(value=current_model)
    model_menu = tk.OptionMenu(scroll_frame, model_var, *MODEL_OPTIONS)
    model_menu.pack(fill="x")

    tk.Label(scroll_frame, text="Site type:").pack(anchor="w")
    type_var = tk.StringVar(value=current_site_type)
    type_menu = tk.OptionMenu(scroll_frame, type_var, *SITE_TYPES)
    type_menu.pack(fill="x")

    tk.Label(scroll_frame, text="Build steps:").pack(anchor="w")
    iter_var = tk.IntVar(value=3)
    iter_entry = tk.Entry(scroll_frame, textvariable=iter_var, width=5)
    iter_entry.pack(anchor="w")

    tk.Label(scroll_frame, text="Website description:").pack(anchor="w")
    prompt_box = scrolledtext.ScrolledText(scroll_frame, width=60, height=6)
    prompt_box.pack(fill="both", expand=True)

    tk.Label(scroll_frame, text="Additional instructions:").pack(anchor="w")
    extra_box = scrolledtext.ScrolledText(scroll_frame, width=60, height=4)
    extra_box.pack(fill="both", expand=True)

    tk.Label(scroll_frame, text="Uploaded images:").pack(anchor="w")
    img_list = tk.Listbox(scroll_frame, width=60, height=4)
    img_list.pack(fill="both", expand=True)

    image_paths: list[str] = []

    tk.Label(scroll_frame, text="Guideline docs:").pack(anchor="w")
    doc_list = tk.Listbox(scroll_frame, width=60, height=4)
    doc_list.pack(fill="both", expand=True)

    doc_paths: list[str] = []

    def fill_from_spec():
        try:
            name, style, colors, desc, extra = parse_spec_file()
        except FileNotFoundError:
            messagebox.showerror("Spec missing", f"{SPEC_FILE} not found")
            return
        name_entry.delete(0, tk.END)
        name_entry.insert(0, name)
        style_entry.delete(0, tk.END)
        style_entry.insert(0, style)
        color_entry.delete(0, tk.END)
        color_entry.insert(0, colors)
        prompt_box.delete("1.0", tk.END)
        prompt_box.insert(tk.END, desc)
        extra_box.delete("1.0", tk.END)
        extra_box.insert(tk.END, extra)

    def add_images():
        paths = filedialog.askopenfilenames(title="Select images")
        for p in paths:
            if p not in image_paths:
                image_paths.append(p)
                img_list.insert(tk.END, os.path.basename(p))

    add_img_btn = tk.Button(scroll_frame, text="Add Images", command=add_images)
    add_img_btn.pack(pady=2)

    def add_docs():
        paths = filedialog.askopenfilenames(title="Select text docs")
        for p in paths:
            if p not in doc_paths:
                doc_paths.append(p)
                doc_list.insert(tk.END, os.path.basename(p))

    add_doc_btn = tk.Button(scroll_frame, text="Add Docs", command=add_docs)
    add_doc_btn.pack(pady=2)

    load_spec_btn = tk.Button(scroll_frame, text="Load Spec", command=fill_from_spec)
    load_spec_btn.pack(pady=2)

    tk.Label(right_frame, text="Conversation:").pack(anchor="w")
    chat_history = scrolledtext.ScrolledText(
        right_frame, width=40, height=10, state=tk.DISABLED
    )
    chat_history.tag_config("user", justify="right", background="#dcf8c6")
    chat_history.tag_config("assistant", justify="left", background="#f0f0f0")
    chat_history.pack(fill="both", expand=True)

    tk.Label(right_frame, text="Chat input:").pack(anchor="w")
    chat_entry = scrolledtext.ScrolledText(right_frame, width=40, height=3)
    chat_entry.pack(fill="both", expand=True)

    site_label = tk.Label(right_frame, text="")
    site_label.pack(anchor="w")

    SITE_INDEX = os.path.abspath(os.path.join("site-dir", "index.html"))

    def update_history():
        chat_history.config(state=tk.NORMAL)
        chat_history.delete("1.0", tk.END)
        for msg in conversation:
            if not msg.get("content"):
                continue
            role = msg.get("role", "")
            tag = "user" if role == "user" else "assistant"
            chat_history.insert(tk.END, msg["content"] + "\n\n", tag)
        chat_history.config(state=tk.DISABLED)

    def open_site():
        site_t = type_var.get()
        if site_t == "react":
            ensure_react_env()
            start_vite_server()
            webbrowser.open(f"http://localhost:{DEV_SERVER_PORT}")
        else:
            if os.path.exists(SITE_INDEX):
                webbrowser.open("file://" + SITE_INDEX)
            else:
                messagebox.showinfo("No site", "index.html not found")

    def run_prompt():
        global current_model
        current_model = model_var.get()
        name = name_entry.get().strip()
        style = style_entry.get().strip()
        colors = color_entry.get().strip()
        desc = prompt_box.get("1.0", tk.END).strip()
        extra = extra_box.get("1.0", tk.END).strip()
        if not desc:
            messagebox.showwarning(
                "Prompt required", "Please enter a website description"
            )
            return
        site_t = type_var.get()
        parts = [f"Business name: {name}" if name else "", desc]
        if style:
            parts.append(f"Design style: {style}")
        if colors:
            parts.append(f"Color scheme: {colors}")
        if extra:
            parts.append(f"Additional instructions: {extra}")
        if image_paths:
            img_names = []
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            for path in image_paths:
                dst = os.path.join(UPLOAD_DIR, os.path.basename(path))
                try:
                    shutil.copy(path, dst)
                    img_names.append(os.path.basename(path))
                except OSError:
                    pass
            if img_names:
                parts.append("Uploaded images: " + ", ".join(img_names))

        if doc_paths:
            doc_texts = []
            os.makedirs(DOCS_DIR, exist_ok=True)
            for path in doc_paths:
                dst = os.path.join(DOCS_DIR, os.path.basename(path))
                try:
                    shutil.copy(path, dst)
                except OSError:
                    pass
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        txt = fh.read()
                    if len(txt) > 2000:
                        txt = txt[:2000]
                    doc_texts.append(f"{os.path.basename(path)}:\n{txt}")
                except (OSError, UnicodeDecodeError):
                    pass
            if doc_texts:
                parts.append("Guideline docs:\n" + "\n\n".join(doc_texts))

        if site_t == "react":
            parts.append("Project type: React")
            ensure_react_env()
        final_prompt = " \n".join(p for p in parts if p)
        iterations = iter_var.get()
        run_btn.config(state=tk.DISABLED)
        try:
            anyio.run(auto_build, final_prompt, iterations, site_t)
            update_history()
            if site_t == "react":
                site_label.config(text=f"Site: http://localhost:{DEV_SERVER_PORT}")
                start_vite_server()
                webbrowser.open(f"http://localhost:{DEV_SERVER_PORT}")
            elif os.path.exists(SITE_INDEX):
                site_label.config(text=f"Site: {SITE_INDEX}")
                webbrowser.open("file://" + SITE_INDEX)
        finally:
            run_btn.config(state=tk.NORMAL)

    run_btn = tk.Button(scroll_frame, text="Run", command=run_prompt)
    run_btn.pack(pady=5)

    def send_chat():
        global current_model
        current_model = model_var.get()
        site_t = type_var.get()
        msg = chat_entry.get("1.0", tk.END).strip()
        if not msg:
            return
        send_btn.config(state=tk.DISABLED)
        try:
            if site_t == "react":
                ensure_react_env()
            anyio.run(call_compound_tool, msg, site_t)
            chat_entry.delete("1.0", tk.END)
            update_history()
            if site_t == "react":
                site_label.config(text=f"Site: http://localhost:{DEV_SERVER_PORT}")
                start_vite_server()
                webbrowser.open(f"http://localhost:{DEV_SERVER_PORT}")
            elif os.path.exists(SITE_INDEX):
                site_label.config(text=f"Site: {SITE_INDEX}")
                webbrowser.open("file://" + SITE_INDEX)
        finally:
            send_btn.config(state=tk.NORMAL)

    send_btn = tk.Button(right_frame, text="Send", command=send_chat)
    send_btn.pack(pady=2)

    open_btn = tk.Button(right_frame, text="Open Site", command=open_site)
    open_btn.pack(pady=2)

    def deploy_vercel():
        try:
            subprocess.run(["vercel", "--prod"], cwd="site-dir", check=True)
            messagebox.showinfo("Vercel", "Deployment complete")
        except Exception:
            messagebox.showwarning(
                "Vercel deploy failed",
                "Ensure the Vercel CLI is installed and you are logged in",
            )

    vercel_btn = tk.Button(right_frame, text="Deploy to Vercel", command=deploy_vercel)
    vercel_btn.pack(pady=2)

    def reset():
        conversation.clear()
        chat_history.config(state=tk.NORMAL)
        chat_history.delete("1.0", tk.END)
        chat_history.config(state=tk.DISABLED)
        chat_entry.delete("1.0", tk.END)
        site_label.config(text="")

    reset_btn = tk.Button(right_frame, text="Reset", command=reset)
    reset_btn.pack(pady=2)

    def on_close():
        server.terminate()
        if vite_process and vite_process.poll() is None:
            vite_process.terminate()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
