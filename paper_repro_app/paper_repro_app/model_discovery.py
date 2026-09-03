from __future__ import annotations

import base64
import json
from typing import Any, Dict


class ModelDiscovery:
    """Discover a standard training entrypoint without binding the runner to one model."""

    result_marker = "PAPER_REPRO_MODEL_JSON="
    env_file_name = ".paper_repro_model.env"

    @classmethod
    def build_remote_script(cls) -> str:
        return (
            "import base64, json, subprocess, sys\n"
            "from pathlib import Path\n"
            "root = Path.cwd()\n"
            "python_bin = sys.argv[1]\n"
            "candidates = [path for name in ('train.py', 'tools/train.py', 'scripts/train.py') if (path := root / name).is_file()]\n"
            "payload = {'entrypoint': '', 'auto_command': '', 'reason': ''}\n"
            "for entrypoint in candidates:\n"
            "    help_result = subprocess.run([python_bin, str(entrypoint), '--help'], cwd=root, capture_output=True, text=True, check=False)\n"
            "    help_text = help_result.stdout + help_result.stderr\n"
            "    if help_result.returncode == 0 and '--data' in help_text:\n"
            "        relative = str(entrypoint.relative_to(root))\n"
            "        payload = {'entrypoint': relative, 'auto_command': f'{python_bin} {relative} --data \"${{PAPER_REPRO_DATA_CONFIG}}\"', 'reason': '识别到标准 train.py 与 --data 参数'}\n"
            "        break\n"
            "if not payload['auto_command']:\n"
            "    payload['reason'] = '未识别到带 --data 参数的标准训练入口；请在页面填写该仓库 README 中的训练命令。'\n"
            "env_path = root / '.paper_repro_model.env'\n"
            "if payload['auto_command']: env_path.write_text('export PAPER_REPRO_AUTO_RUN_COMMAND=' + json.dumps(payload['auto_command']) + '\\n', encoding='utf-8')\n"
            "print('PAPER_REPRO_MODEL_JSON=' + base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii'))"
        )

    @classmethod
    def build_remote_command(cls, python_bin: str) -> str:
        encoded = base64.b64encode(cls.build_remote_script().encode("utf-8")).decode("ascii")
        return f"{python_bin} -c 'import base64; exec(base64.b64decode(\"{encoded}\"))' {python_bin}"

    @classmethod
    def extract_payload(cls, log_text: str) -> Dict[str, Any]:
        for line in reversed(log_text.splitlines()):
            if line.startswith(cls.result_marker):
                try:
                    return json.loads(base64.b64decode(line[len(cls.result_marker):]).decode("utf-8"))
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    return {}
        return {}
