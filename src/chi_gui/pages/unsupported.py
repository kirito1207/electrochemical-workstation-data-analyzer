"""Unsupported-technique page copy."""


def unsupported_message(technique: str) -> str:
    return f"{technique}：当前版本尚未支持该技术，需要专用 parser 和分析模块。"
