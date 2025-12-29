import os
import subprocess
import sys
import signal

COMMIT_MESSAGES = [
    "Renamed 'Armature Mapper' to 'Humanoid Armature Mapper.",
    "Removed the property 'Is NPR' for 'SourcePBR' conversion.",
    "Moved 'Split Active Weights Linearly' to bone section.",
    "Revised translation code for faster processing.",
    "Importing mesh with shapekeys will set their value to 0 for Blender 5.0",
    "Fixed repeated print for mesh face deletion on the console",
    "Added preserve basis normals on the console print",
    "Added Emissive map on PseudoPBR 'SourcePBR' model",
    "Deleted unused proputils.py",
    "PseudoPBR 'Alpha only' and 'RGB' share the same exponent process for metal",
    "Renamed tool operator ids to 'kitsunetools'",
]

BUMP_VERSION = "272"

def signal_handler(sig, frame):
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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
    print("=== Git Push ===\n")
    
    print(f"\n--- Commit message ---")
    for msg in COMMIT_MESSAGES:
        print(msg)
    print(f"Bump version to {BUMP_VERSION}")
    print("----------------------\n")
    
    print("--- Executing git commands ---\n")
    
    if not run_command("git add ."):
        sys.exit(1)
    
    full_message = "\n".join(COMMIT_MESSAGES) + f"\nBump version to {BUMP_VERSION}"
    
    result = subprocess.run(["git", "commit", "-m", full_message], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing commit")
        print(result.stderr)
        sys.exit(1)
    if result.stdout:
        print(result.stdout.strip())
    
    print("\nReady to push to remote...")
    confirm = input("Continue? (y/n): ").lower()
    if confirm != 'y':
        print("\nAborted. Reverting commit...")
        run_command("git reset --soft HEAD~1")
        print("✓ Commit reverted")
        sys.exit(0)
    
    if not run_command("git push --force"):
        sys.exit(1)
    
    print("\n✓ All done!")

if __name__ == "__main__":
    main()