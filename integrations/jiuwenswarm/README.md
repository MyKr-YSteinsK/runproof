# RPF-95 read-only MCP adapter

Historical evidence only. Run the stdio module from a new `.local/rpf-95-jiuwenswarm/<32-hex-owner>` working directory with the repository on `PYTHONPATH` and the task-owned Python environment. Set `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `UV_CACHE_DIR`, `PIP_CACHE_DIR`, `TEMP` and `TMP` to absolute paths inside that owner. The server rejects missing or external paths before constructing FastMCP; its working-directory guard prevents FastMCP's default `.env` lookup from using the repository root. Do not expose the service as a general file reader or write endpoint.

The three tools are `get_capabilities`, `inspect_recorded_experiment` and `verify_witness`. Input is restricted to fixed source IDs; output is derived from the existing RPF-47 source verifier and offline Witness verifier. Anchored content does not establish issuer authenticity. RPF-46 is a redacted historical summary; RPF-43/44 are separate sessions.

Validation: from the repository root, run the owner virtual environment's Python with `-B -m unittest discover -s integrations/jiuwenswarm/tests -p 'test_*.py' -v`. The owner Python must have `mcp==1.30.0`. Complete JiuwenSwarm dependencies and its manager registration are not included or certified by this integration.
