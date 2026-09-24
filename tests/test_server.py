"""Tests for the cross-platform API server entry point."""

import asyncio

from app.server import create_selector_loop


def test_create_selector_loop_returns_selector_loop() -> None:
    loop = create_selector_loop()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()
