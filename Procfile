# Process types for Heroku-style orchestration.
# Docker/Railway production uses ENTRYPOINT (/entrypoint.sh) — do not set a duplicate start command.
web: PROCESS_TYPE=web /entrypoint.sh
worker: PROCESS_TYPE=worker /entrypoint.sh
beat: PROCESS_TYPE=beat /entrypoint.sh
transfer-worker: PROCESS_TYPE=transfer-worker /entrypoint.sh
