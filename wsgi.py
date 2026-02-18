#!/usr/bin/env python3
"""
WSGI entry point for production deployment.
Use with Gunicorn or other WSGI servers.

Example usage:
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import the Flask app
from app_new import app

if __name__ == "__main__":
    app.run()
