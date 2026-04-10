"""Entry point: python -m scripts.webui"""

import uvicorn


def main():
    uvicorn.run(
        "scripts.webui.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
