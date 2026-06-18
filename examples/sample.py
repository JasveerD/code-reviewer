def divide(a, b):
    return a / b   # no zero check, intentional

def fetch(url):
    import urllib.request
    return urllib.request.urlopen(url).read()   # no timeout, no validation
