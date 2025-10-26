#! python3

import zipfile, os, re

script_dir = os.path.join("io_scene_valvesource")

with open(os.path.join(script_dir, "__init__.py")) as vs_init:
    content = vs_init.read()
    ver_match = re.search(r'ADDONVER\s*=\s*(\d+)', content)
    state_match = re.search(r'ADDONDEVSTATE\s*=\s*[\'"](\w+)[\'"]', content)
    
    if not ver_match:
        print("Error: ADDONVER not found in __init__.py")
        exit(1)
    
    ver_num = int(ver_match.group(1))
    dev_state = state_match.group(1) if state_match else ""

if ver_num < 10:
    version_str = f"0.{ver_num}"
elif ver_num < 100:
    major = ver_num // 10
    minor = ver_num % 10
    version_str = f"{major}.{minor}"
else:
    major = ver_num // 100
    minor = (ver_num % 100) // 10
    patch = ver_num % 10
    version_str = f"{major}.{minor}.{patch}"

if dev_state:
    zip_name = f"kitsunesourcetool_{version_str}_{dev_state.lower()}.zip"
else:
    zip_name = f"kitsunesourcetool_{version_str}.zip"

print(f"Creating release: {zip_name}")

zip_file = zipfile.ZipFile(os.path.join("..", zip_name), 'w', zipfile.ZIP_BZIP2)

for path, dirnames, filenames in os.walk(script_dir):
    if path.endswith("__pycache__"): 
        continue
    for f in filenames:
        f = os.path.join(path, f)
        zip_file.write(os.path.realpath(f), f)

zip_file.close()
print(f"✓ Release created: ../{zip_name}")