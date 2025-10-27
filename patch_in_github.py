import os
import re
import subprocess
import sys
import atexit
import signal

INIT_FILE = "io_scene_valvesource/__init__.py"
original_version = None
push_completed = False

def cleanup_on_exit():
    global original_version, push_completed
    if original_version is not None and not push_completed:
        print("\n\n⚠ Script interrupted! Reverting version...")
        revert_addon_version(original_version)
        print("✓ Version reverted")

def signal_handler(sig, frame):
    sys.exit(1)

atexit.register(cleanup_on_exit)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def update_addon_version():
    if not os.path.exists(INIT_FILE):
        print(f"Error: {INIT_FILE} not found!")
        return None, None
    
    with open(INIT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'ADDONVER\s*=\s*(\d+)', content)
    if not match:
        print("Error: ADDONVER not found in __init__.py")
        return None, None
    
    current_ver = int(match.group(1))
    new_ver = current_ver + 1
    
    new_content = re.sub(
        r'ADDONVER\s*=\s*\d+',
        f'ADDONVER = {new_ver}',
        content
    )
    
    with open(INIT_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✓ Version bumped: {current_ver} → {new_ver}")
    return current_ver, new_ver

def revert_addon_version(original_ver):
    if original_ver is None:
        return
    
    with open(INIT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = re.sub(
        r'ADDONVER\s*=\s*\d+',
        f'ADDONVER = {original_ver}',
        content
    )
    
    with open(INIT_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✓ Version reverted to: {original_ver}")

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing: {cmd}")
        print(result.stderr)
        return False
    if result.stdout:
        print(result.stdout.strip())
    return True

def main():
    global original_version, push_completed
    
    print("=== Git Push with Version Bump ===\n")
    
    original_version, new_ver = update_addon_version()
    if original_version is None:
        sys.exit(1)
    
    print("\nEnter commit messages (press Enter on empty line to finish):\n")
    
    messages = []
    line_num = 1
    while True:
        msg = input(f"{line_num}: ").strip()
        if not msg:
            if not messages:
                print("Error: At least one commit message is required!")
                continue
            break
        messages.append(msg)
        line_num += 1
    
    print(f"\n--- Commit message ---")
    for msg in messages:
        print(msg)
    print("----------------------\n")
    
    print("--- Executing git commands ---\n")
    
    if not run_command("git add ."):
        revert_addon_version(original_version)
        sys.exit(1)
    
    commit_cmd_parts = ["git", "commit"]
    for msg in messages:
        commit_cmd_parts.extend(["-m", msg])
    
    result = subprocess.run(commit_cmd_parts, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing commit")
        print(result.stderr)
        revert_addon_version(original_version)
        sys.exit(1)
    if result.stdout:
        print(result.stdout.strip())
    
    print("\nPushing to remote...")
    confirm = input("Continue? (y/n): ").lower()
    if confirm != 'y':
        print("\nAborted. Reverting changes...")
        run_command("git reset --soft HEAD~1")
        revert_addon_version(original_version)
        print("✓ Commit and version reverted")
        sys.exit(0)
    
    if not run_command("git push --force"):
        revert_addon_version(original_version)
        sys.exit(1)
    
    push_completed = True
    print("\n✓ All done!")

if __name__ == "__main__":
    main()