"""
Run this instead of uvicorn directly.
It starts the FastAPI server AND opens an ngrok tunnel,
then prints the public URL to paste into your Lovable project.
"""
from dotenv import load_dotenv
load_dotenv()

import os
import uvicorn
import threading
from pyngrok import ngrok, conf

NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN", "")
NGROK_ENABLED = os.getenv("NGROK_ENABLED", "").lower() == "true"
PORT = 8000


def start_ngrok():
    if NGROK_AUTH_TOKEN:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
    ngrok.kill()  # kill any existing ngrok process before starting
    tunnel = ngrok.connect(PORT, "http")
    public_url = tunnel.public_url
    print("\n" + "=" * 60)
    print(f"  NGROK PUBLIC URL: {public_url}")
    print(f"  Paste this into Lovable as your API_BASE_URL:")
    print(f"  {public_url}")
    print("=" * 60 + "\n")
    return public_url


if __name__ == "__main__":
    # Start ngrok in a background thread only if enabled
    if NGROK_ENABLED:
        ngrok_thread = threading.Thread(target=start_ngrok, daemon=True)
        ngrok_thread.start()
        ngrok_thread.join(timeout=5)  # wait for URL to print
    else:
        print("\n  Ngrok is disabled. Set NGROK_ENABLED=true to enable.\n")

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
