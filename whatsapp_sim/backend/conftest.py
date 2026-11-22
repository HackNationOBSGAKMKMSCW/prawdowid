"""Testy adaptera: limit zapytań na klienta sprawdzają osobne testy (z własną bramką)."""

import os

os.environ["CHECK_RATE_LIMIT"] = "off"
