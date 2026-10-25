from __future__ import annotations


def legacy_args(command: str, remainder: list[str]) -> list[str]:
    if command in {"start", "stop"} and remainder[:1] == ["--"]:
        # argparse.REMAINDER needs a separator to accept lifecycle options.
        # Remove it before legacy parsing; preserve chat's message separator.
        remainder = remainder[1:]
    mapping = {
        "start": ["--daemon-start"],
        "stop": ["--daemon-stop"],
        "chat": ["--chat"],
        "chat-gpt": ["--chat-gpt"],
    }
    return mapping[command] + list(remainder)
