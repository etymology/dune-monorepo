import uvicorn
import argparse


def main():
    parser = argparse.ArgumentParser(description="Dune Tension Web Interface")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()

    uvicorn.run(
        "dune_tension.api.main:app", host=args.host, port=args.port, reload=False
    )


if __name__ == "__main__":
    main()
