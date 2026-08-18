#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time

request = json.load(sys.stdin)
role = str(request.get("role") or "worker")
node_id = str(request.get("node_id") or role)

# Small delay makes parallel research lanes visible in telemetry/backpressure demos.
if role == "researcher":
    time.sleep(0.05)

usage = {
    "input_tokens": 25,
    "output_tokens": 12,
    "cost_usd": 0.0001,
    "provider": "mock-runtime",
    "model": request.get("model_tier"),
}

if role == "grader":
    output = {
        "decision": "pass",
        "score": 0.99,
        "failures": [],
        "evidence": ["mock deterministic grader evidence"],
        "usage": usage,
    }
elif role == "integrator":
    output = {
        "answer": "Payment status updates are asynchronous and the queue path is the relevant implementation boundary.",
        "summary": "Integrated worker evidence.",
        "usage": usage,
    }
else:
    output = {
        "summary": f"{role} completed {node_id}",
        "findings": [
            {
                "claim": "Payment status updates are asynchronous",
                "evidence": f"mock evidence from {node_id}",
                "source": f"runtime:{node_id}",
                "confidence": 0.9,
                "canonicalKey": "payment|status-update-mode",
                "value": "async"
            }
        ],
        "usage": usage,
    }

json.dump(output, sys.stdout, ensure_ascii=False)
