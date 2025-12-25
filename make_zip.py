#! python3

import zipfile, os, re

script_dir = os.path.join("io_scene_valvesource")
toml_path = os.path.join(script_dir, "blender_manifest.toml")

with open(toml_path) as toml_file:
    content = toml_file.read()
    version_match = re.search(r'^version\s*=\s*[\'"]?([0-9.]+)[\'"]?', content, re.MULTILINE)
    
    if not version_match:
        print("Error: version not found in blender_manifest.toml")
        exit(1)
    
    version_str = version_match.group(1)
    
    wheels_section = re.search(r'wheels\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if not wheels_section:
        print("Error: wheels section not found in blender_manifest.toml")
        exit(1)
    
    wheel_lines = re.findall(r'[\'"](.+?)[\'"]', wheels_section.group(1))

platforms = {
    'win_amd64': 'windows',
    'macosx_11_0_arm64': 'macos_arm',
    'macosx_10_10_x86_64': 'macos_intel',
    'manylinux': 'linux'
}

def get_platform_from_wheel(wheel_path):
    for platform_tag, platform_name in platforms.items():
        if platform_tag in wheel_path:
            return platform_name
    return None

wheel_platform_map = {}
for wheel in wheel_lines:
    platform = get_platform_from_wheel(wheel)
    if platform:
        if platform not in wheel_platform_map:
            wheel_platform_map[platform] = []
        wheel_platform_map[platform].append(wheel)

print(f"Creating platform-specific releases for version {version_str}\n")

for platform_name, platform_wheels in wheel_platform_map.items():
    zip_name = f"kitsunesourcetool_{version_str}_{platform_name}.zip"
    print(f"Creating {zip_name}...")
    
    zip_file = zipfile.ZipFile(os.path.join("..", zip_name), 'w', zipfile.ZIP_BZIP2)
    
    for path, dirnames, filenames in os.walk(script_dir):
        if path.endswith("__pycache__"):
            continue
        
        for f in filenames:
            file_path = os.path.join(path, f)
            relative_path = os.path.relpath(file_path, ".")
            
            if file_path.endswith(".whl"):
                should_include = False
                for platform_wheel in platform_wheels:
                    wheel_filename = os.path.basename(platform_wheel)
                    if file_path.endswith(wheel_filename):
                        should_include = True
                        break
                
                if not should_include:
                    continue
            
            zip_file.write(file_path, relative_path)
    
    zip_file.close()
    zip_size = os.path.getsize(os.path.join("..", zip_name)) / (1024 * 1024)
    print(f"  ✓ {zip_name} ({zip_size:.2f} MB)")

print(f"\n✓ All platform releases created in ../")