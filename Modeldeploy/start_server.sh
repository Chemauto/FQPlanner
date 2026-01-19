#!/bin/bash
python -m vllm.entrypoints.openai.api_server \
  --model /home/dora/RoboBrain2.0/Model_3B \
  --host 0.0.0.0 \
  --port 4567 \
  --served-model-name robobrain \
  --gpu-memory-utilization 0.90 \
  --max-model-len 10000 \
  --max-num-seqs 256 \
  --trust-remote-code \
  --enable-chunked-prefill \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --chat-template /home/dora/RoboOs/RoboOS/deploy/templates/tool_chat_template_hermes.jinja
