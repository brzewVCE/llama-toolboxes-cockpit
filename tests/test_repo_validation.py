"""ponytail: one runnable check for repo format validation logic."""


def is_valid_hf_repo(repo: str) -> bool:
    """Mirrors the validation gate in model_handlers._handle_download."""
    repo = repo.strip()
    if "/" not in repo or len(repo.split("/")) != 2 or not all(repo.split("/")):
        return False
    return True


# Good repos
assert is_valid_hf_repo("unsloth/GLM-5.2-GGUF")
assert is_valid_hf_repo("  unsloth/GLM-5.2-GGUF  ")  # whitespace stripped

# Garbage / accidental input
assert not is_valid_hf_repo("")
assert not is_valid_hf_repo("   ")
assert not is_valid_hf_repo("asdfghjkl")
assert not is_valid_hf_repo("(.venv) ")
assert not is_valid_hf_repo("/")
assert not is_valid_hf_repo("owner/")
assert not is_valid_hf_repo("/model")
assert not is_valid_hf_repo("a/b/c")

print("All checks passed.")
