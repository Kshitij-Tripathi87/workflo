"""Adapter used by the application to read a provider response."""


def response_text(payload: dict) -> str:
    return payload["text"]
