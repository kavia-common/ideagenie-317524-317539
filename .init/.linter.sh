#!/bin/bash
cd /home/kavia/workspace/code-generation/ideagenie-317524-317539/ai_idea_generator_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

