import urllib.request
import json
from pathlib import Path

def download_pillow_wheels():
    addon_dir = Path(__file__).parent
    wheels_dir = addon_dir / "io_scene_valvesource" / "wheels"
    wheels_dir.mkdir(exist_ok=True)
    
    platforms = [
        ("cp311", "win_amd64"),
        ("cp311", "macosx_11_0_arm64"),
        ("cp311", "macosx_10_10_x86_64"),
        ("cp311", "manylinux_2_28_x86_64"),
    ]
    
    print("Fetching Pillow releases from PyPI...")
    pypi_url = "https://pypi.org/pypi/pillow/json"
    
    with urllib.request.urlopen(pypi_url) as response:
        data = json.loads(response.read())
    
    version = data["info"]["version"]
    print(f"Latest Pillow version: {version}\n")
    
    for python_version, platform_tag in platforms:
        target_whl = None
        for url_info in data["urls"]:
            if url_info["packagetype"] == "bdist_wheel":
                filename = url_info["filename"]
                if python_version in filename and platform_tag in filename:
                    target_whl = url_info
                    break
        
        if not target_whl:
            print(f"No wheel found for {platform_tag}")
            continue
        
        whl_path = wheels_dir / target_whl["filename"]
        
        if whl_path.exists():
            print(f"✓ {target_whl['filename']} (already exists)")
        else:
            print(f"Downloading {target_whl['filename']}...")
            urllib.request.urlretrieve(target_whl["url"], whl_path)
            print(f"✓ Downloaded ({whl_path.stat().st_size // 1024 // 1024}MB)")
    
    print(f"\n✓ All wheels ready in ./wheels/")
    print("\nUpdate your blender_manifest.toml with:")
    print("wheels = [")
    for whl in sorted(wheels_dir.glob("*.whl")):
        print(f'    "./wheels/{whl.name}",')
    print("]")

if __name__ == "__main__":
    download_pillow_wheels()