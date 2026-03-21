from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


WEB_DIR = Path(__file__).resolve().parent
REPO_DIR = WEB_DIR.parent
REPORT_DIR = REPO_DIR / "artifacts" / "reports"
STRATEGY_DIR = REPO_DIR / "strategy"
SELECTED_FACTOR_DIR = REPO_DIR / "artifacts" / "selected_factors"
CACHE_DIR = REPO_DIR / "artifacts" / "cache" / "ohlcv"
ENV_FILE = REPO_DIR / ".env"
RUNTIME_CONFIG = REPO_DIR / "config" / "runtime.yaml"
SYMBOLS_FILE = REPO_DIR / "config" / "symbols.txt"
DEFAULT_PORT = 8765

DEFAULT_FACTORS = [
    "momentum_20",
    "momentum_60",
    "trend_pullback_20_5",
    "reversal_3",
    "reversal_5",
    "low_volatility_20",
    "vol_compression_10_40",
    "true_range_pct_1",
    "volume_surprise_5",
    "turnover_shock_20",
    "liquidity_20",
    "breakout_distance_20",
    "close_location_1",
    "gap_continuation_1",
    "ma_distance_20",
]

TASKS: dict[str, dict[str, Any]] = {}
TASK_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def pick_python_executable() -> str:
    candidates = [
        os.environ.get("QUANT_WEB_PYTHON"),
        r"C:\ProgramData\miniconda3\envs\quant\python.exe",
        sys.executable,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return sys.executable


def clean_scalar(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def clean_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    else:
        raw_items = list(value)
    cleaned = [str(item).strip() for item in raw_items if str(item).strip()]
    return cleaned or None


def add_flag(args: list[str], flag: str, value: Any) -> None:
    value = clean_scalar(value)
    if value is None:
        return
    args.extend([flag, str(value)])


def add_multi_flag(args: list[str], flag: str, values: Any) -> None:
    cleaned = clean_list(values)
    if not cleaned:
        return
    args.append(flag)
    args.extend(cleaned)


def add_boolean_toggle(args: list[str], positive_flag: str, negative_flag: str, value: Any) -> None:
    if value is True:
        args.append(positive_flag)
    elif value is False:
        args.append(negative_flag)


def build_workflow_command(workflow: str, params: dict[str, Any]) -> list[str]:
    workflow = workflow.strip()
    args: list[str] = [workflow]

    if workflow == "factor-pipeline":
        add_flag(args, "--train-start", params.get("train_start"))
        add_flag(args, "--train-end", params.get("train_end"))
        add_flag(args, "--oos-start", params.get("oos_start"))
        add_flag(args, "--oos-end", params.get("oos_end"))
        add_flag(args, "--walk-forward-start", params.get("walk_forward_start"))
        add_flag(args, "--walk-forward-end", params.get("walk_forward_end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        add_flag(args, "--top-n", params.get("top_n"))
        add_flag(args, "--rebalance-every-n-days", params.get("rebalance_every_n_days"))
        add_flag(args, "--train-years", params.get("train_years"))
        add_flag(args, "--test-months", params.get("test_months"))
        add_flag(args, "--step-months", params.get("step_months"))
        add_flag(args, "--gap-days", params.get("gap_days"))
        add_boolean_toggle(args, "--overwrite-frozen", "--no-overwrite-frozen", params.get("overwrite_frozen"))
        return args

    if workflow == "factor-research":
        add_flag(args, "--train-start", params.get("train_start"))
        add_flag(args, "--train-end", params.get("train_end"))
        add_flag(args, "--oos-start", params.get("oos_start"))
        add_flag(args, "--oos-end", params.get("oos_end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        return args

    if workflow == "factor-select":
        add_flag(args, "--train-start", params.get("train_start"))
        add_flag(args, "--train-end", params.get("train_end"))
        add_flag(args, "--oos-start", params.get("oos_start"))
        add_flag(args, "--oos-end", params.get("oos_end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        add_boolean_toggle(args, "--overwrite-frozen", "--no-overwrite-frozen", params.get("overwrite_frozen"))
        return args

    if workflow == "composite-backtest":
        add_flag(args, "--train-start", params.get("train_start"))
        add_flag(args, "--train-end", params.get("train_end"))
        add_flag(args, "--oos-start", params.get("oos_start"))
        add_flag(args, "--oos-end", params.get("oos_end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        add_flag(args, "--top-n", params.get("top_n"))
        add_flag(args, "--rebalance-every-n-days", params.get("rebalance_every_n_days"))
        return args

    if workflow == "factor-walk-forward":
        add_flag(args, "--start", params.get("start"))
        add_flag(args, "--end", params.get("end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        add_flag(args, "--train-years", params.get("train_years"))
        add_flag(args, "--test-months", params.get("test_months"))
        add_flag(args, "--step-months", params.get("step_months"))
        add_flag(args, "--gap-days", params.get("gap_days"))
        add_flag(args, "--top-n", params.get("top_n"))
        return args

    if workflow == "alpha-combo-search":
        add_flag(args, "--train-start", params.get("train_start"))
        add_flag(args, "--train-end", params.get("train_end"))
        add_flag(args, "--oos-start", params.get("oos_start"))
        add_flag(args, "--oos-end", params.get("oos_end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        add_flag(args, "--top-n", params.get("top_n"))
        add_flag(args, "--rebalance-every-n-days", params.get("rebalance_every_n_days"))
        return args

    if workflow == "alpha-combo-walk-forward":
        add_flag(args, "--start", params.get("start"))
        add_flag(args, "--end", params.get("end"))
        add_multi_flag(args, "--candidate-factors", params.get("candidate_factors"))
        add_flag(args, "--train-years", params.get("train_years"))
        add_flag(args, "--test-months", params.get("test_months"))
        add_flag(args, "--step-months", params.get("step_months"))
        add_flag(args, "--gap-days", params.get("gap_days"))
        add_flag(args, "--top-n", params.get("top_n"))
        add_flag(args, "--rebalance-every-n-days", params.get("rebalance_every_n_days"))
        return args

    if workflow == "alpha-combo-risk-search":
        add_flag(args, "--train-start", params.get("train_start"))
        add_flag(args, "--train-end", params.get("train_end"))
        add_flag(args, "--oos-start", params.get("oos_start"))
        add_flag(args, "--oos-end", params.get("oos_end"))
        add_flag(args, "--target-max-dd", params.get("target_max_dd"))
        add_multi_flag(args, "--gross-exposure-grid", params.get("gross_exposure_grid"))
        add_multi_flag(args, "--top-n-grid", params.get("top_n_grid"))
        add_multi_flag(args, "--stop-loss-grid", params.get("stop_loss_grid"))
        add_multi_flag(args, "--trailing-stop-grid", params.get("trailing_stop_grid"))
        add_multi_flag(args, "--max-holding-days-grid", params.get("max_holding_days_grid"))
        return args

    if workflow == "train":
        add_flag(args, "--start", params.get("start"))
        add_flag(args, "--end", params.get("end"))
        add_multi_flag(args, "--strategies", params.get("strategies"))
        add_flag(args, "--objective", params.get("objective"))
        if params.get("overwrite_frozen") is True:
            args.append("--overwrite-frozen")
        return args

    if workflow == "test":
        add_flag(args, "--start", params.get("start"))
        add_flag(args, "--end", params.get("end"))
        add_multi_flag(args, "--strategies", params.get("strategies"))
        return args

    if workflow == "walk-forward":
        add_flag(args, "--start", params.get("start"))
        add_flag(args, "--end", params.get("end"))
        add_multi_flag(args, "--strategies", params.get("strategies"))
        add_flag(args, "--train-years", params.get("train_years"))
        add_flag(args, "--test-months", params.get("test_months"))
        add_flag(args, "--step-months", params.get("step_months"))
        add_flag(args, "--gap-days", params.get("gap_days"))
        return args

    if workflow == "pipeline":
        add_flag(args, "--optimize-start", params.get("optimize_start"))
        add_flag(args, "--optimize-end", params.get("optimize_end"))
        add_flag(args, "--test-start", params.get("test_start"))
        add_flag(args, "--test-end", params.get("test_end"))
        add_flag(args, "--walk-forward-start", params.get("walk_forward_start"))
        add_flag(args, "--walk-forward-end", params.get("walk_forward_end"))
        add_multi_flag(args, "--candidate-strategies", params.get("candidate_strategies"))
        add_flag(args, "--objective", params.get("objective"))
        add_flag(args, "--max-strategies", params.get("max_strategies"))
        add_flag(args, "--train-years", params.get("train_years"))
        add_flag(args, "--test-months", params.get("test_months"))
        add_flag(args, "--step-months", params.get("step_months"))
        add_flag(args, "--gap-days", params.get("gap_days"))
        add_boolean_toggle(args, "--overwrite-frozen", "--no-overwrite-frozen", params.get("overwrite_frozen"))
        return args

    if workflow == "deploy":
        if params.get("dry_run", True):
            args.append("--dry-run")
        return args

    raise ValueError(f"Unsupported workflow: {workflow}")


def shell_preview(command: list[str]) -> str:
    escaped_parts: list[str] = []
    for part in command:
        if any(char.isspace() for char in part) or '"' in part:
            escaped_parts.append('"' + part.replace('"', '\\"') + '"')
        else:
            escaped_parts.append(part)
    return " ".join(escaped_parts)


def parse_json_maybe(text: str) -> Any | None:
    payload = text.strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(payload[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def list_reports() -> list[dict[str, Any]]:
    if not REPORT_DIR.exists():
        return []

    entries: list[dict[str, Any]] = []
    for path in sorted(REPORT_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        markdown_path = path.with_suffix(".md")
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "stem": path.stem,
                "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                "size": stat.st_size,
                "has_markdown": markdown_path.exists(),
                "markdown_name": markdown_path.name if markdown_path.exists() else None,
            }
        )
    return entries


def discover_factor_names() -> list[str]:
    for entry in list_reports():
        try:
            payload = json.loads((REPORT_DIR / entry["name"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        for candidate in (
            payload.get("research", {}).get("engine", {}).get("factor_names"),
            payload.get("research", {}).get("train", {}).get("factor_names"),
        ):
            if candidate:
                return [str(item) for item in candidate]
    return DEFAULT_FACTORS.copy()


def discover_strategy_names() -> list[str]:
    if not STRATEGY_DIR.exists():
        return []
    names = []
    for path in sorted(STRATEGY_DIR.iterdir()):
        if path.is_dir() and not path.name.startswith("__"):
            names.append(path.name)
    return names


def read_env_keys() -> set[str]:
    if not ENV_FILE.exists():
        return set()
    keys: set[str] = set()
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=" not in clean:
                continue
            key = clean.split("=", 1)[0].strip()
            if key:
                keys.add(key)
    except OSError:
        return set()
    return keys


def count_symbols() -> int:
    if not SYMBOLS_FILE.exists():
        return 0
    count = 0
    try:
        for line in SYMBOLS_FILE.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                count += 1
    except OSError:
        return 0
    return count


def build_readiness_payload() -> dict[str, Any]:
    env_keys = read_env_keys()
    alpaca_ready = {"ALPACA_API_KEY", "ALPACA_API_SECRET"}.issubset(env_keys) or {
        "ALPACA_PAPER1_API_KEY_ID",
        "ALPACA_PAPER1_API_SECRET_KEY",
    }.issubset(env_keys)
    email_ready = {
        "EMAIL_SENDER",
        "EMAIL_PASSWORD",
        "EMAIL_RECEIVER",
        "SMTP_HOST",
        "SMTP_PORT",
    }.issubset(env_keys)
    runtime_ready = RUNTIME_CONFIG.exists()
    report_count = len(list_reports())
    cache_count = len(list(CACHE_DIR.glob("*.csv"))) if CACHE_DIR.exists() else 0
    frozen_models = len(list(SELECTED_FACTOR_DIR.glob("*.json"))) if SELECTED_FACTOR_DIR.exists() else 0
    symbols_count = count_symbols()

    checks = [
        {
            "key": "alpaca",
            "label": "Alpaca 凭证",
            "status": "ready" if alpaca_ready else "missing",
            "detail": "已检测到 paper 凭证变量" if alpaca_ready else "缺少 ALPACA_API_KEY / ALPACA_API_SECRET",
        },
        {
            "key": "email",
            "label": "邮件通知",
            "status": "ready" if email_ready else "optional",
            "detail": "自动邮件通知已基本就绪" if email_ready else "未配全邮箱参数，不影响本地回测",
        },
        {
            "key": "runtime",
            "label": "运行期配置",
            "status": "ready" if runtime_ready else "missing",
            "detail": "runtime.yaml 已存在" if runtime_ready else "缺少 config/runtime.yaml",
        },
        {
            "key": "symbols",
            "label": "股票池",
            "status": "ready" if symbols_count > 0 else "missing",
            "detail": f"当前股票池数量: {symbols_count}",
        },
        {
            "key": "reports",
            "label": "历史报告",
            "status": "ready" if report_count > 0 else "empty",
            "detail": f"可读取报告数: {report_count}",
        },
        {
            "key": "cache",
            "label": "本地缓存",
            "status": "ready" if cache_count > 0 else "cold",
            "detail": f"OHLCV 缓存文件数: {cache_count}",
        },
        {
            "key": "models",
            "label": "冻结模型",
            "status": "ready" if frozen_models > 0 else "empty",
            "detail": f"selected_factors / 模型文件数: {frozen_models}",
        },
    ]

    blockers = [item["detail"] for item in checks if item["status"] == "missing"]
    nudges = [item["detail"] for item in checks if item["status"] in {"optional", "cold", "empty"}]
    return {
        "checks": checks,
        "blockers": blockers,
        "nudges": nudges,
        "env_file_exists": ENV_FILE.exists(),
    }


def task_snapshot(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task["id"],
        "workflow": task["workflow"],
        "status": task["status"],
        "created_at": task["created_at"],
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "command": task["command"],
        "params": task["params"],
        "log": task["log"],
        "result_json": task.get("result_json"),
        "new_reports": task.get("new_reports", []),
        "return_code": task.get("return_code"),
        "can_cancel": bool(task.get("process")) and task.get("status") in {"queued", "running", "cancelling"},
    }


def latest_reports_since(start_ts: float) -> list[str]:
    if not REPORT_DIR.exists():
        return []
    new_names: list[str] = []
    for path in REPORT_DIR.glob("*.json"):
        if path.stat().st_mtime >= start_ts:
            new_names.append(path.name)
    new_names.sort(key=lambda name: (REPORT_DIR / name).stat().st_mtime, reverse=True)
    return new_names


def run_task(task_id: str) -> None:
    with TASK_LOCK:
        task = TASKS[task_id]
        task["status"] = "running"
        task["started_at"] = utc_now_iso()
        start_ts = time.time()

    process_env = os.environ.copy()
    process_env["PYTHONUTF8"] = "1"
    command = task["command_parts"]

    process = subprocess.Popen(
        command,
        cwd=str(REPO_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=process_env,
    )
    with TASK_LOCK:
        task = TASKS[task_id]
        task["process"] = process

    output_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output_lines.append(line)
        with TASK_LOCK:
            task = TASKS[task_id]
            task["log"] = "".join(output_lines)[-120000:]

    return_code = process.wait()
    output_text = "".join(output_lines)

    with TASK_LOCK:
        task = TASKS[task_id]
        task["return_code"] = return_code
        task["finished_at"] = utc_now_iso()
        task["log"] = output_text[-120000:]
        task["result_json"] = parse_json_maybe(output_text)
        task["new_reports"] = latest_reports_since(start_ts)
        task["process"] = None
        if task.get("cancellation_requested"):
            task["status"] = "cancelled"
        else:
            task["status"] = "success" if return_code == 0 else "failed"


def create_task(workflow: str, params: dict[str, Any]) -> dict[str, Any]:
    command_parts = [pick_python_executable(), str(REPO_DIR / "main.py"), *build_workflow_command(workflow, params)]
    task_id = uuid.uuid4().hex[:10]
    task = {
        "id": task_id,
        "workflow": workflow,
        "status": "queued",
        "created_at": utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "command": shell_preview(command_parts),
        "command_parts": command_parts,
        "params": params,
        "log": "",
        "result_json": None,
        "new_reports": [],
        "return_code": None,
        "process": None,
        "cancellation_requested": False,
    }

    with TASK_LOCK:
        TASKS[task_id] = task

    thread = threading.Thread(target=run_task, args=(task_id,), daemon=True)
    thread.start()
    return task_snapshot(task)


def cancel_task(task_id: str) -> dict[str, Any]:
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            raise KeyError("Task not found.")
        process = task.get("process")
        if task.get("status") not in {"queued", "running", "cancelling"}:
            return task_snapshot(task)
        task["cancellation_requested"] = True
        task["status"] = "cancelling"

    if process and process.poll() is None:
        process.terminate()

    with TASK_LOCK:
        return task_snapshot(TASKS[task_id])


def load_report_file(name: str) -> tuple[dict[str, Any], int]:
    path = (REPORT_DIR / name).resolve()
    if REPORT_DIR.resolve() not in path.parents or not path.exists():
        return {"error": "Report not found."}, HTTPStatus.NOT_FOUND

    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"error": f"Failed to read report: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR
        return {"name": path.name, "content_type": "json", "content": payload}, HTTPStatus.OK

    if path.suffix.lower() == ".md":
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"error": f"Failed to read markdown: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR
        return {"name": path.name, "content_type": "markdown", "content": content}, HTTPStatus.OK

    return {"error": "Unsupported file type."}, HTTPStatus.BAD_REQUEST


def build_meta_payload() -> dict[str, Any]:
    return {
        "repo_dir": str(REPO_DIR),
        "web_dir": str(WEB_DIR),
        "python_executable": pick_python_executable(),
        "strategies": discover_strategy_names(),
        "factors": discover_factor_names(),
        "reports": list_reports()[:8],
        "server_time_utc": utc_now_iso(),
    }


class QuantWorkbenchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


    def read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            self.send_json({"ok": True, "time": utc_now_iso()})
            return

        if path == "/api/meta":
            self.send_json(build_meta_payload())
            return

        if path == "/api/readiness":
            self.send_json(build_readiness_payload())
            return

        if path == "/api/reports":
            self.send_json({"items": list_reports()})
            return

        if path == "/api/report":
            name = clean_scalar(query.get("name", [None])[0])
            if not name:
                self.send_json({"error": "Missing report name."}, HTTPStatus.BAD_REQUEST)
                return
            payload, status = load_report_file(unquote(str(name)))
            self.send_json(payload, status)
            return

        if path == "/api/tasks":
            with TASK_LOCK:
                tasks = [task_snapshot(task) for task in TASKS.values()]
            tasks.sort(key=lambda item: item["created_at"], reverse=True)
            self.send_json({"items": tasks})
            return

        if path.startswith("/api/tasks/"):
            task_id = path.split("/")[-1]
            with TASK_LOCK:
                task = TASKS.get(task_id)
                snapshot = task_snapshot(task) if task else None
            if not snapshot:
                self.send_json({"error": "Task not found."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(snapshot)
            return

        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/cancel"):
            task_id = parsed.path.split("/")[-2]
            try:
                snapshot = cancel_task(task_id)
            except KeyError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(snapshot)
            return

        if parsed.path != "/api/tasks":
            self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self.read_json_body()
            workflow = str(payload.get("workflow", "")).strip()
            params = payload.get("params") or {}
            if not workflow:
                raise ValueError("Workflow is required.")
            task = create_task(workflow, params)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        self.send_json(task, HTTPStatus.CREATED)


def main() -> None:
    port = int(os.environ.get("QUANT_WEB_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("127.0.0.1", port), QuantWorkbenchHandler)
    print(f"Quant local workbench running at http://127.0.0.1:{port}")
    print(f"Repo root: {REPO_DIR}")
    print(f"Python for tasks: {pick_python_executable()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
