"""Toy module for testing the reviewer."""
import os
import urllib.request


def divide(a, b):
    return a / b


async def fetch(url):
    return urllib.request.urlopen(url).read()


class Calculator:
    def __init__(self):
        self.history = []

    def add(self, x, y):
        result = x + y
        self.history.append(result)
        return result

    def reset(self):
        self.history = []
