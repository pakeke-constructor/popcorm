
from _ex6.provider_openai import invoke_llm as invoke_llm_openai
from _ex6.models import M
from _ex6.agents import auto_setup
from _ex6.tools import read_headers, read_body, glob, search, write_file, edit_file, read_file, edit_file_lines, escalate, bash, explore_agent, CLAUDE_MD, ENV_PROMPT, git_working_tree, add_tool_repetition_guard, powershell, ask_user_question
from _ex6.skills import load_skill
from _ex6.tasks import plan_add_log, plan_done, plan_list, plan_read, plan_write
from _ex6.web_tools import websearch_agent
from _ex6.provider import cache_manually
import ex6
from ex6 import Context, Message



def setup(app: ex6.App):
    tui = app.tui; assert tui

    auto_setup(app)

