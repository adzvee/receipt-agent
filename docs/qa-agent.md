# The Q&A agent

`POST /chat` answers plain-English questions by running a small agent loop
(`app/agent/agent.py`):

1. The question (plus earlier turns, for follow-ups) goes to the LLM along with
   descriptions of four tools: `spending_summary`, `list_receipts`, `get_receipt`, and
   `search_line_items`.
2. The LLM either answers, or asks for one or more tools with specific arguments.
3. Our code validates the arguments, runs the tool, and sends the result back. Repeat,
   up to 6 steps. On the last step the model isn't allowed to call tools and is told to
   answer from what it has found.

An empty result says so explicitly ("this account has no receipts yet, this is a complete
answer"). Without that, the model treated `[]` as a possible mistake and kept re-checking
with broader filters until it ran out of steps. Now "How much did I spend on food last
month?" on an empty account is one tool call and "$0, no receipts in that period".

**The LLM never writes SQL.** It can only choose a predefined tool and fill in typed
arguments (dates, categories from a fixed list, a vendor name), which are validated before
anything runs. Each tool is a fixed, parameterized SQLAlchemy `SELECT`
(`app/agent/tools.py`). As a second line of defense, the chat request runs in a Postgres
`READ ONLY` transaction with a 5-second statement timeout, so even a buggy tool couldn't
modify data.

Other guard rails: invalid tool calls are returned to the model as errors so it can
correct itself; spending totals skip unreadable receipts and open duplicates; different
currencies are never added together; and receipt text in tool results is treated as data,
not instructions.
