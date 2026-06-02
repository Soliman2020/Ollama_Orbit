import os
from typing import Dict, List

import dotenv

# Load environment variables from a .env file (if present) at project root.
dotenv.load_dotenv()

# Configure your Ollama accounts here.
# Each account must have a unique name and a storage state file
# that will be created by the login routine.

ACCOUNTS: List[Dict] = [
    {
        "name": "msoliman",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_1"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_1"),
        "storage": "app/state_account_1.json",
    },
    {
        "name": "rut-tassel",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_2"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_2"),
        "storage": "app/state_account_2.json",
    },
    {
        "name": "humbly-swoosh",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_3"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_3"),
        "storage": "app/state_account_3.json",
    },
    {
        "name": "foe-unruly",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_4"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_4"),
        "storage": "app/state_account_4.json",
    },
    {
        "name": "poking-jot",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_5"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_5"),
        "storage": "app/state_account_5.json",
    },
    {
        "name": "gmail",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_6"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_6"),
        "storage": "app/state_account_6.json",
    },
    # Add four more accounts as needed
]

# How often to refresh the usage snapshot (in minutes).
REFRESH_MINUTES: int = 10

# URL of the Ollama settings usage page.
SETTINGS_URL: str = "https://ollama.com/settings"
