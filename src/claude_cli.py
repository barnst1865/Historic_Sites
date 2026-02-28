"""
Shared helper for calling the Claude Code CLI (`claude -p`) as a subprocess.

Replaces direct Anthropic SDK usage — uses the local Claude Code installation
(authenticated via Claude Max subscription) instead of a separate API key.
"""

import logging
import os
import subprocess

from config.settings import CLAUDE_CLI_TIMEOUT

logger = logging.getLogger(__name__)


def call_claude(
    prompt: str,
    system_prompt: str | None = None,
    model: str = "sonnet",
    timeout: int | None = None,
) -> str | None:
    """Run a text-only prompt through `claude -p`.

    Args:
        prompt: The user prompt to send.
        system_prompt: Optional system prompt (prepended to the user prompt).
        model: CLI model alias (e.g. "sonnet", "opus", "haiku").
        timeout: Subprocess timeout in seconds (defaults to CLAUDE_CLI_TIMEOUT).

    Returns:
        Response text, or None on failure.
    """
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"
    else:
        full_prompt = prompt

    cmd = [
        "claude",
        "-p",
        "--model", model,
        "--output-format", "text",
        "--tools", "",
    ]

    return _run_cli(cmd, full_prompt, timeout)


def call_claude_with_file(
    file_path: str,
    prompt: str,
    system_prompt: str | None = None,
    model: str = "sonnet",
    timeout: int | None = None,
) -> str | None:
    """Run a prompt through `claude -p` with the Read tool enabled.

    Claude CLI's Read tool handles PDFs natively — no base64 encoding needed.

    Args:
        file_path: Absolute path to the file for Claude to read.
        prompt: The user prompt (should reference the file).
        system_prompt: Optional system prompt.
        model: CLI model alias.
        timeout: Subprocess timeout in seconds.

    Returns:
        Response text, or None on failure.
    """
    full_prompt = f"Read the file at {file_path} and then:\n\n"
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{full_prompt}"
    full_prompt += prompt

    cmd = [
        "claude",
        "-p",
        "--model", model,
        "--output-format", "text",
        "--tools", "Read",
    ]

    return _run_cli(cmd, full_prompt, timeout)


def _run_cli(cmd: list[str], prompt: str, timeout: int | None) -> str | None:
    """Execute the claude CLI subprocess.

    Pipes the prompt via stdin to avoid shell escaping issues with long prompts.
    Unsets the CLAUDECODE env var so the CLI doesn't refuse to run inside a
    Claude Code session.
    """
    timeout = timeout or CLAUDE_CLI_TIMEOUT

    # Build a clean environment — remove CLAUDECODE so the CLI runs normally
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        if result.returncode != 0:
            logger.warning(
                "Claude CLI returned exit code %d: %s",
                result.returncode,
                result.stderr[:500] if result.stderr else "(no stderr)",
            )
            return None

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        logger.error(
            "Claude CLI not found. Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
        )
        return None
    except Exception as e:
        logger.warning("Claude CLI call failed: %s", e)
        return None
