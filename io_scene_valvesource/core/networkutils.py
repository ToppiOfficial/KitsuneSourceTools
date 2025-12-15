import urllib.request
import urllib.parse
import json
import time
import re
from typing import Union, List

def translate_string(text: Union[str, List[str]], source_lang: str = 'auto', delay: float = 0.15) -> Union[str, List[str]]:
    """
    Translate text using Google Translate API with safeguards against rate limiting.
    Preserves numeric suffixes in names (e.g., "上半身2" -> "upper_body2")
    """
    
    def _extract_suffix(name: str) -> tuple:
        """Extract numeric suffix from name"""
        match = re.search(r'(\d+)$', name)
        if match:
            return (name[:match.start()], match.group(1))
        return (name, None)
    
    def _translate_single(text_str: str) -> str:
        """Translate a single string"""
        if not text_str or not text_str.strip():
            return text_str
        
        base, suffix = _extract_suffix(text_str)
        
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': source_lang,
            'tl': 'en',
            'dt': 't',
            'q': base
        }
        
        url_with_params = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url_with_params)
        request.add_header('User-Agent', 'Mozilla/5.0')
        
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                translated = ''.join([item[0] for item in result[0] if item[0]])
                
                if suffix:
                    return f"{translated}{suffix}"
                return translated
                
        except Exception as e:
            print(f"Translation error for '{text_str}': {e}")
            return text_str
    
    if isinstance(text, str):
        return _translate_single(text)
    
    elif isinstance(text, list):
        if not text:
            return []
        
        results = []
        unique_bases = {}
        
        for item in text:
            base, suffix = _extract_suffix(item)
            if base not in unique_bases:
                unique_bases[base] = None
        
        for i, base in enumerate(unique_bases.keys()):
            translated_base = _translate_single(base)
            unique_bases[base] = translated_base
            
            if i < len(unique_bases) - 1:
                time.sleep(delay)
        
        for item in text:
            base, suffix = _extract_suffix(item)
            translated_base = unique_bases.get(base, base)
            if suffix:
                results.append(f"{translated_base}{suffix}")
            else:
                results.append(translated_base)
        
        return results
    
    else:
        raise TypeError("Input must be str or list of str")