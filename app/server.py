"""Development server entry point with a Psycopg-compatible Windows event loop."""

import argparse
import asyncio
import sys

import uvicorn


def create_selector_loop() -> asyncio.AbstractEventLoop:
    """Create the selector loop required by Psycopg on Windows."""
    return asyncio.SelectorEventLoop()


def main() -> None:
    """Run the FastAPI application with development-friendly options."""
    parser = argparse.ArgumentParser(description="Run the Sekuro API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--reload", action="store_true")
    arguments = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
        loop=create_selector_loop if sys.platform == "win32" else "auto",
    )


if __name__ == "__main__":
    main()
