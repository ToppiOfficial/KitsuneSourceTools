import os
import subprocess
import sys
import signal

COMMIT_MESSAGES = [
    "Sanitize function now allows non-latin characters.",
    "Exporting materials now have their names sanitized.",
    "Set max input character length for bone export name to 256 characters.",
    "Removed name validation for shapekeys due to irrelevance and performance hit.",
    "Duplicated export names are now marked as .001, .002, etc. which follows Blender's convention.",
    "Revised Armature Mapper, now includes the following inputs: Upperarm, Forearm, and Knee.",
    "Subdivide bone now relies on Blender's bone duplicate naming i.e. .001, .002 rather than 1, 2, 3.",
    "PseudoPBR process now uses Pillow or PIL.",
    "Fixed PseudoPBR conversion array error due to image dimensions not matching.",
    "PBR to Phong now takes the max size of the alpha channel as the export image dimension rather than the image dimension.",
    "Added separate input for alpha channel, will default to all opaque if none are provided.",
    "Removed unused property groups.",
    "Merged some property groups.",
    "Removed help and version dropdown.",
    "Object properties dropdown no longer gets disabled on mismatched object type.",
    "Removed propagate function.",
    "Fixed shapekey counting duplicates.",
    "Swapped 'Add ToonEdgeLine' operator booleans to enum.",
    "Add Edgeline operator now creates a vertex group named 'Edgeline_Thickness' rather than 'non_exportable_faces'.",
    "Fixed constant error for Vertex and Float Maps"
    "Normalizing weights now only considered deform bones"
]

BUMP_VERSION = "271"

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