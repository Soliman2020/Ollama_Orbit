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
        "name": "Account_1",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_1"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_1"),
        "storage": "app/state_account_1.json",
    },
    {
        "name": "Account_2",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_2"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_2"),
        "storage": "app/state_account_2.json",
    },
    {
        "name": "Account_3",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_3"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_3"),
        "storage": "app/state_account_3.json",
    },
    {
        "name": "Account_4",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_4"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_4"),
        "storage": "app/state_account_4.json",
    },
    {
        "name": "Account_5",
        "plan": "Free",
        "email": os.getenv("OLLAMA_EMAIL_5"),  # example, replace per account
        "password": os.getenv("OLLAMA_PASSWORD_5"),
        "storage": "app/state_account_5.json",
    },
    {
        "name": "Account_6",
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
