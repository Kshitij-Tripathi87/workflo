"""Pinned, offline checks for the mock provider's two response versions."""

from integration import response_text


def test_existing_provider_contract():
    assert response_text({"text": "hello"}) == "hello"


def test_incoming_provider_contract():
    assert response_text({"output_text": "hello"}) == "hello"
