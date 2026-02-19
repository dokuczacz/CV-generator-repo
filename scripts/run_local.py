#!/usr/bin/env python3
"""
run_local.py

Cross-platform (Windows-focused) local development launcher for CV-generator-repo.
- Stops processes listening on given ports (7071, 3000, 10000-10002)
- Creates logs and .azurite directories
- Opens new PowerShell windows to run:
  - Azurite (blob storage emulator)
  - Azure Functions (func start)
  - Next.js UI (npm run dev)

Usage:
  python scripts/run_local.py [--skip-install] [--ports 7071 3000 10000 10001 10002]

Note: Intended for Windows with PowerShell, Azure Functions Core Tools, and npm/pnpm.
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(repo_root: Path):
    logs = repo_root / "tmp" / "logs"
    azurite = repo_root / ".azurite"
    logs.mkdir(parents=True, exist_ok=True)
    azurite.mkdir(parents=True, exist_ok=True)
    return logs, azurite


def find_pids_on_port_windows(port: int) -> list[int]:
    """Uses netstat -ano and parses lines with LISTENING and the port."""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5:
            proto = parts[0]
            local = parts[1]
            state = parts[3] if len(parts) >= 4 else ""
            pid = parts[-1]
            if proto.lower().startswith("tcp") and state.upper() == "LISTENING":
                if local.endswith(f":{port}") or local.endswith(f".{port}"):
                    try:
                        pids.add(int(pid))
                    except Exception:
                        continue
    return list(pids)


def kill_pid_windows(pid: int):
    try:
        subprocess.check_call(["taskkill", "/PID", str(pid), "/F"], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Stopped PID {pid}")
    except subprocess.CalledProcessError:
        print(f"Failed to stop PID {pid}")


def stop_processes_on_ports(ports: list[int]):
    if os.name == 'nt':
        for port in ports:
            pids = find_pids_on_port_windows(port)
            if not pids:
                continue
            for pid in pids:
                kill_pid_windows(pid)
    else:
        # Unix: use lsof
        for port in ports:
            try:
                out = subprocess.check_output(["lsof", "-i", f":{port}", "-t"], text=True)
                for line in out.splitlines():
                    try:
                        pid = int(line.strip())
                        os.kill(pid, 9)
                        print(f"Stopped PID {pid} on port {port}")
                    except Exception:
                        pass
            except Exception:
                pass


def start_powershell_window(title: str, command: str, working_directory: Path):
    """Use cmd start to open new window with PowerShell Core (pwsh) or Windows PowerShell."""
    ps_command = (
        f"$host.UI.RawUI.WindowTitle = '{title}'; "
        f"Set-Location -LiteralPath '{working_directory}'; "
        f"{command}"
    )
    if os.name == 'nt':
        # Try pwsh first, fall back to powershell
        ps_exe = "pwsh.exe" if shutil.which("pwsh") else "powershell.exe"
        cmd = [
            "cmd.exe", "/c", "start", ps_exe, 
            "-NoExit", "-ExecutionPolicy", "Bypass", 
            "-Command", ps_command
        ]
        subprocess.Popen(cmd)
    else:
        # On non-Windows just spawn a shell in background
        subprocess.Popen(["/bin/sh", "-c", command], cwd=str(working_directory))


def available_executable(name: str) -> bool:
    return shutil.which(name) is not None


def main():
    repo_root = get_repo_root()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ports", nargs="*", type=int, 
        default=[7071, 3000, 10000, 10001, 10002]
    )
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    logs_dir, azurite_location = ensure_dirs(repo_root)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    azurite_debug_log = logs_dir / f"azurite_debug_{ts}.log"
    azurite_log = logs_dir / f"azurite_{ts}.log"
    func_log = logs_dir / f"func_{ts}.log"
    ui_log = logs_dir / f"ui_{ts}.log"

    print("Stopping processes on ports:", args.ports)
    stop_processes_on_ports(args.ports)

    # Check for .venv
    venv_path = repo_root / '.venv'
    activate = venv_path / 'Scripts' / 'Activate.ps1'
    if not activate.exists():
        print("Warning: .venv not found. Run setup manually if needed.")

    # Prepare commands
    azurite_cmd = None
    if available_executable('azurite'):
        azurite_cmd = (
            f"azurite --location '{azurite_location}' "
            f"--debug '{azurite_debug_log}' 2>&1 | Tee-Object -FilePath '{azurite_log}'"
        )
    elif available_executable('npx'):
        azurite_cmd = (
            f"npx --yes azurite --location '{azurite_location}' "
            f"--debug '{azurite_debug_log}' 2>&1 | Tee-Object -FilePath '{azurite_log}'"
        )
    else:
        azurite_cmd = (
            "Write-Host 'Azurite not found. Install it (npm i -g azurite) "
            "or ensure npx is available.'; exit 1"
        )

    # Azure Functions command (runs from repo root where function_app.py lives)
    func_command = (
        f"& '{activate}'; "
        "if (-not (Get-Command func -ErrorAction SilentlyContinue)) { "
        "  throw 'Azure Functions Core Tools (`func`) not found. Install it, then re-run.' "
        "}; "
        f"func start 2>&1 | Tee-Object -FilePath '{func_log}'"
    )

    # Next.js UI command (runs from ui/ directory)
    ui_command = (
        "if (Get-Command pnpm -ErrorAction SilentlyContinue) { "
        f"  pnpm dev 2>&1 | Tee-Object -FilePath '{ui_log}' "
        "} elseif (Get-Command npm -ErrorAction SilentlyContinue) { "
        f"  npm run dev 2>&1 | Tee-Object -FilePath '{ui_log}' "
        "} else { "
        "  Write-Host 'pnpm or npm not found. Install and retry.'; exit 1 "
        "}"
    )

    # Start windows
    print("Starting Azurite window...")
    start_powershell_window('Azurite', azurite_cmd, repo_root)

    print("Starting Azure Functions window...")
    start_powershell_window('Azure Functions (func start)', func_command, repo_root)

    print("Starting Next.js UI window...")
    start_powershell_window('Next.js UI (npm run dev)', ui_command, repo_root / 'ui')

    print("\n=== Started ===")
    print(f"  - Azurite (stdout/stderr): {azurite_log}")
    print(f"  - Azurite (debug):         {azurite_debug_log}")
    print(f"  - Functions log:           {func_log}")
    print(f"  - UI log:                  {ui_log}")
    print("  - Next.js UI:              http://localhost:3000")
    print("  - Azure Functions:         http://localhost:7071")
    print("  - Azurite:                 http://localhost:10000 (blob), 10001 (queue), 10002 (table)")
    print("\nAll services are running in separate windows. Close windows to stop services.")


if __name__ == '__main__':
    main()
