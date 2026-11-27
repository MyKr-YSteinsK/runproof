"""Measure the actual text-mode prompt with the pinned public DeepSeek encoder, offline."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from .rpf119_protocol import TOKENIZER_REFERENCE
from .timeout_experiment import require


def measure(folder, body):
    raw = (folder / "encoding.py").read_bytes()
    vocab = (folder / "tokenizer.json").read_bytes()
    require(sha256(raw).hexdigest() == TOKENIZER_REFERENCE["encoder_sha256"]
            and sha256(vocab).hexdigest() == TOKENIZER_REFERENCE["tokenizer_sha256"], "TOKENIZER_SOURCE")
    tokenizer = json.loads(vocab)
    require(tokenizer["model"]["type"] == "BPE" and tokenizer["decoder"]["type"] == "ByteLevel"
            and any(p["type"] == "ByteLevel" and p["add_prefix_space"] is False
                    for p in tokenizer["pre_tokenizer"]["pretokenizers"]), "TOKENIZER_BYTE_BOUND")
    # Only the hash-pinned encoder runs, in the separate keyless meter process.
    namespace = {"__name__": "published_deepseek_encoder"}
    exec(compile(raw, "published_deepseek_encoder", "exec"), namespace)
    messages = body["messages"]
    messages[0]["tools"] = body["tools"]
    rendered = namespace["encode_messages"](messages, thinking_mode="chat")
    return len(rendered.encode("utf-8"))


if __name__ == "__main__":
    print(measure(Path(sys.argv[1]), json.loads(sys.stdin.buffer.read(32768))))
