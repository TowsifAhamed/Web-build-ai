import os
import sys
import subprocess
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import shutil
import anyio
import webbrowser
from mcp.client.session_group import ClientSessionGroup, SseServerParameters

MCP_PORT = 4876
MCP_URL = f"http://localhost:{MCP_PORT}/sse"
UPLOAD_DIR = os.path.join("site-dir", "uploads")
DOCS_DIR = os.path.join("site-dir", "docs")
MODEL = os.getenv("MCP_MODEL", "meta-llama/llama-4-maverick-17b-128e-instruct")

# conversation history for revision prompts
conversation: list[dict] = []

async def call_compound_tool(prompt: str) -> str:
    """Send the next user prompt using the conversation history."""
    conversation.append({"role": "user", "content": prompt})
    async with ClientSessionGroup() as group:
        session = await group.connect_to_server(SseServerParameters(url=MCP_URL))
        result = await session.call_tool("compound_tool", {"messages": conversation, "model": MODEL})
        text_blocks = [b.text for b in result.content if hasattr(b, "text")]
        text = "".join(text_blocks) if text_blocks else ""
        conversation.append({"role": "assistant", "content": text})
        return text

def start_server() -> subprocess.Popen:
    return subprocess.Popen([
        sys.executable,
        "website_mcp.py",
        "--port",
        str(MCP_PORT),
        "--transport",
        "sse",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def main():
    server = start_server()
    root = tk.Tk()
    root.title("Website Builder")

    tk.Label(root, text="Business name:").pack(anchor="w")
    name_entry = tk.Entry(root, width=80)
    name_entry.pack(fill="x")

    tk.Label(root, text="Design style:").pack(anchor="w")
    style_entry = tk.Entry(root, width=80)
    style_entry.pack(fill="x")

    tk.Label(root, text="Color scheme:").pack(anchor="w")
    color_entry = tk.Entry(root, width=80)
    color_entry.pack(fill="x")

    tk.Label(root, text="Website description:").pack(anchor="w")
    prompt_box = scrolledtext.ScrolledText(root, width=80, height=6)
    prompt_box.pack(fill="both", expand=True)

    tk.Label(root, text="Additional instructions:").pack(anchor="w")
    extra_box = scrolledtext.ScrolledText(root, width=80, height=4)
    extra_box.pack(fill="both", expand=True)

    tk.Label(root, text="Uploaded images:").pack(anchor="w")
    img_list = tk.Listbox(root, width=80, height=4)
    img_list.pack(fill="both", expand=True)

    image_paths: list[str] = []

    tk.Label(root, text="Guideline docs:").pack(anchor="w")
    doc_list = tk.Listbox(root, width=80, height=4)
    doc_list.pack(fill="both", expand=True)

    doc_paths: list[str] = []

    def add_images():
        paths = filedialog.askopenfilenames(title="Select images")
        for p in paths:
            if p not in image_paths:
                image_paths.append(p)
                img_list.insert(tk.END, os.path.basename(p))

    add_img_btn = tk.Button(root, text="Add Images", command=add_images)
    add_img_btn.pack(pady=2)

    def add_docs():
        paths = filedialog.askopenfilenames(title="Select text docs")
        for p in paths:
            if p not in doc_paths:
                doc_paths.append(p)
                doc_list.insert(tk.END, os.path.basename(p))

    add_doc_btn = tk.Button(root, text="Add Docs", command=add_docs)
    add_doc_btn.pack(pady=2)

    tk.Label(root, text="Conversation:").pack(anchor="w")
    chat_history = scrolledtext.ScrolledText(root, width=80, height=10, state=tk.DISABLED)
    chat_history.pack(fill="both", expand=True)

    tk.Label(root, text="Chat input:").pack(anchor="w")
    chat_entry = scrolledtext.ScrolledText(root, width=80, height=3)
    chat_entry.pack(fill="both", expand=True)

    site_label = tk.Label(root, text="")
    site_label.pack(anchor="w")

    SITE_INDEX = os.path.abspath(os.path.join("site-dir", "index.html"))

    def update_history():
        chat_history.config(state=tk.NORMAL)
        chat_history.delete("1.0", tk.END)
        for msg in conversation:
            if not msg.get("content"):
                continue
            role = msg.get("role", "").capitalize()
            chat_history.insert(tk.END, f"{role}: {msg['content']}\n\n")
        chat_history.config(state=tk.DISABLED)

    def open_site():
        if os.path.exists(SITE_INDEX):
            webbrowser.open("file://" + SITE_INDEX)
        else:
            messagebox.showinfo("No site", "index.html not found")

    def run_prompt():
        name = name_entry.get().strip()
        style = style_entry.get().strip()
        colors = color_entry.get().strip()
        desc = prompt_box.get("1.0", tk.END).strip()
        extra = extra_box.get("1.0", tk.END).strip()
        if not desc:
            messagebox.showwarning("Prompt required", "Please enter a website description")
            return
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

        final_prompt = " \n".join(p for p in parts if p)
        run_btn.config(state=tk.DISABLED)
        try:
            anyio.run(call_compound_tool, final_prompt)
            update_history()
            if os.path.exists(SITE_INDEX):
                site_label.config(text=f"Site: {SITE_INDEX}")
                webbrowser.open("file://" + SITE_INDEX)
        finally:
            run_btn.config(state=tk.NORMAL)

    run_btn = tk.Button(root, text="Run", command=run_prompt)
    run_btn.pack(pady=5)

    def send_chat():
        msg = chat_entry.get("1.0", tk.END).strip()
        if not msg:
            return
        send_btn.config(state=tk.DISABLED)
        try:
            anyio.run(call_compound_tool, msg)
            chat_entry.delete("1.0", tk.END)
            update_history()
            if os.path.exists(SITE_INDEX):
                site_label.config(text=f"Site: {SITE_INDEX}")
        finally:
            send_btn.config(state=tk.NORMAL)

    send_btn = tk.Button(root, text="Send", command=send_chat)
    send_btn.pack(pady=2)

    open_btn = tk.Button(root, text="Open Site", command=open_site)
    open_btn.pack(pady=2)

    def reset():
        conversation.clear()
        chat_history.config(state=tk.NORMAL)
        chat_history.delete("1.0", tk.END)
        chat_history.config(state=tk.DISABLED)
        chat_entry.delete("1.0", tk.END)
        site_label.config(text="")

    reset_btn = tk.Button(root, text="Reset", command=reset)
    reset_btn.pack(pady=2)

    def on_close():
        server.terminate()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
