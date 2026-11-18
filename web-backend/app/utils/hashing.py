import hashlib
def hash_identifier(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()
