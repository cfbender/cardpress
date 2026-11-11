"""Run the Cardpress web service."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="cardpress", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (default 8765)")
    args = parser.parse_args()
    uvicorn.run("cardpress.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
