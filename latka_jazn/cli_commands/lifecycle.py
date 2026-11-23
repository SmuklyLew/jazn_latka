from __future__ import annotations


def legacy_args(command: str, remainder: list[str]) -> list[str]:
    if command in {"start", "stop"} and "--" in remainder:
        # Historical lifecycle separator may follow --root and other options.
        # Chat's message separator remains untouched.
        index = remainder.index("--")
        remainder = remainder[:index] + remainder[index + 1:]
    mapping = {
        "start": ["--daemon-start"],
        "stop": ["--daemon-stop"],
        "chat": ["--chat"],
        "chat-gpt": ["--chat-gpt"],
    }
    return mapping[command] + list(remainder)
