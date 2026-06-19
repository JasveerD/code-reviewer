"""Toy module for testing the reviewer."""
import hashlib
import subprocess
import urllib.request

API_KEY = "sk-prod-abc123XYZ"   # security: hardcoded secret


def divide(a, b):
    return a / b   # correctness: no zero check


async def fetch(url):
    return urllib.request.urlopen(url).read()   # correctness + security


def get_user(user_id: int) -> dict | None:
    if user_id < 0:
        return None
    return {"id": user_id, "name": "test"}


def greet():
    user = get_user(42)
    return user["name"].upper()   # correctness: user may be None


def run_command(user_input: str):
    subprocess.run(f"echo {user_input}", shell=True)   # security: command injection


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()   # security: weak hash


def find_duplicates(items: list) -> list:
    duplicates = []
    for i, item in enumerate(items):
        for j, other in enumerate(items):
            if i != j and item == other and item not in duplicates:
                duplicates.append(item)
    return duplicates   # performance: O(n²) where set gives O(n)


def squares(n: int) -> list[int]:
    result = []
    for i in range(n):
        result.append(i * i)   # performance: should be list comprehension (PERF401)
    return result
