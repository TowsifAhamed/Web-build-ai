# Web Build AI

This repository contains an MCP server that can generate HTML and CSS files for modern websites using Groq's language models.

## Setup

First create a Python 3.12 virtual environment and install the required packages:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For React projects you also need Node.js and npm available in your PATH.

Create a `.env` file in the project root and add your Groq API key:

```bash
echo "GROQ_API_KEY=your_key_here" > .env
echo "GEMINI_API_KEY=your_gemini_key" >> .env
```
The `GEMINI_API_KEY` is optional and only required if you plan to run the agent
with Google's Gemini models (model names starting with `gemini`). Both
`website_mcp.py` and the graphical UI automatically load this `.env` file, so
the keys do not need to be exported globally.

## Running the server

Launch the server with:

```bash
python website_mcp.py --port 4876 --transport sse
```

The server creates a `site-dir/` directory which acts as a sandbox for generated files. It is automatically added to `.gitignore`.
Each time a file inside `site-dir/` is written via the `write_file` tool, its contents
are embedded using a small SentenceTransformer model and stored in
`site-dir/embeddings.json`. Only files that change are re-embedded, keeping
bandwidth and token usage low.

## Using the UI

To run the server and a simple graphical interface in one step, use:

```bash
python website_builder_ui.py
```

When the UI opens you can provide a detailed design concept:

1. **Business name** – the name or brand for the site.
2. **Design style** – e.g. modern, minimal, playful.
3. **Color scheme** – main colors to use.
4. **Model** – choose from Groq and Gemini models using the drop-down.
5. **Site type** – select either *html* or *react*.
6. **Website description** – a short overview of the pages or layout.
7. **Additional instructions** – any extra features or notes.
8. **Uploaded images** – optional logos or product pictures you want to include.
9. **Guideline docs** – text files with design briefs or other requirements.

Selecting **react** initializes a simple React project inside `site-dir/` the first time you build. Subsequent runs reuse that environment.
When building a React project the agent calls `get_os` to report the current operating system and `init_react_project` to create the environment using Vite and npm.

Use **Add Images** to select image files from your computer. They will be copied
into `site-dir/uploads/` and listed in the UI. Mention them in your prompt or
let the agent know how to use them.

Use **Add Docs** to select text guidelines. They are copied into
`site-dir/docs/` and the contents are added to your prompt so the model follows
your requirements.

Press **Load Spec** to automatically populate the fields using `docs/spec.md` if
it exists.

Fill in these fields and click **Run**. The generated HTML and CSS files will appear inside `site-dir/`.

Each time you press **Run**, your prompt is added to the conversation so you can
refine the site with follow-up instructions. Use the **Reset** button to start a
fresh conversation. When generation finishes the UI opens the site for you. For
plain HTML projects it loads `site-dir/index.html`. When you choose the React
site type it automatically runs `npm run dev` and opens `http://localhost:5173`.
You can also press **Open Site** at any time to view the latest version.

When you're happy with the output you can deploy directly to Vercel by clicking
**Deploy to Vercel**. Make sure the Vercel CLI is installed and that you're
logged in first.

The interface also includes a chat area that displays the full conversation.
You can send additional messages in the **Chat input** box and press **Send** to
continue iterating on the site. The latest assistant replies and your prompts
appear in the **Conversation** window so you can track changes easily.

## Using the agent

You can call the `compound_tool` function programmatically to instruct the agent to build a website. Example:

```python
from website_mcp import compound_tool
import asyncio

messages = [
    {
        "role": "user",
        "content": (
            "Business name: Brewed Awakenings\n"
            "Design style: modern minimal\n"
            "Color scheme: earth tones\n"
            "Create a landing page advertising weekly specials"
        ),
    }
]

html = asyncio.run(compound_tool(messages))
```

The generated site will be written inside `site-dir/` using the agent's tools.

All file paths passed to tools like `write_file` or `read_file` must be
relative to `site-dir/` (for example `index.html` or `css/main.css`). Do not
prefix paths with `site-dir/`. Absolute paths are rejected to keep generation
contained within the sandbox.

You can keep the `messages` list and append more `{"role": "user"}` entries to
perform revisions. Each call to `compound_tool` returns the assistant response
which you can also add back into the list for a persistent conversation.

The MCP server also exposes a `search_docs` tool that retrieves snippets from
files in `site-dir/docs/`. Provide a query string and the tool will return any
matching text, enabling a simple retrieval-augmented workflow.

## Deploying on Vercel

The generated site is a static project inside `site-dir/`, so it can be
deployed using [Vercel](https://vercel.com). Install the Vercel CLI with:

```bash
npm install -g vercel
```

Then run the following commands from the project root:

```bash
cd site-dir
vercel --prod
```

Vercel will prompt you for a project name and optionally create a
`vercel.json` file. Both plain HTML/CSS sites and the React build output work
with this workflow.

The UI also exposes a **Deploy to Vercel** button that runs these commands for
you.

## Deploying on AWS with NGINX

Below is a minimal outline for serving the UI on an EC2 instance:

1. Launch an Ubuntu server and SSH into it.
2. Install Python 3.12, NGINX and Git.
3. Clone this repository and follow the setup instructions above.
4. Start `website_mcp.py` using a process manager such as `systemd` or `tmux`.
5. Configure NGINX to forward requests to the MCP server:

    ```nginx
    server {
        listen 80;
        server_name your_domain_or_ip;

        location / {
            proxy_pass http://127.0.0.1:4876;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
    ```

6. Restart NGINX and browse to your domain to access the builder.

## License

This project is distributed under the Business Source License 1.1. See the
[LICENSE](LICENSE) file for the license text and usage terms.
