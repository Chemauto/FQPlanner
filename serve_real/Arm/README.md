# Real Arm Grasp Bridge

This bridge lets the LLM grasp tool run the MuJoCo simulation first, then optionally trigger the project-local real grasp server.

Enable it in `serve_real/config.yaml`:

```yaml
real_arm:
  enabled: 1
  host: 127.0.0.1
  port: 9999
  timeout: 60
  command_byte: 0xAA
  fail_on_error: 1
```

For a board-side server, set `host` to the board IP, for example `192.168.0.155`. The server must accept byte `0xAA` and return `SUCCESS...` or `FAILED...`.

In this repository, the compatible server is:

```bash
python3 serve_real/Arm/grasp_server.py
```

By default it runs this absolute path:

```bash
/home/fangqi/camera_10s.sh
```

The script should exit `0` on success and non-zero on failure.

Environment variables override the YAML values:

- `REAL_ARM_ENABLED`
- `REAL_ARM_HOST`
- `REAL_ARM_PORT`
- `REAL_ARM_TIMEOUT`
- `REAL_ARM_COMMAND_BYTE`
- `REAL_ARM_FAIL_ON_ERROR`

Server-side environment variables:

- `REAL_ARM_SERVER_HOST`
- `REAL_ARM_SERVER_PORT`
- `REAL_ARM_SCRIPT_PATH`
- `REAL_ARM_SCRIPT_TIMEOUT`
