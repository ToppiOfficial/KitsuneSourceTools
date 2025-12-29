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

    def _translate_batch(text_list: List[str]) -> List[str]:
        """Translate a batch of strings in a single API call."""
        def _fallback_individual() -> List[str]:
            """Fallback to translating items one by one."""
            results = []
            for i, item in enumerate(text_list):
                results.append(_translate_single(item))
                if i < len(text_list) - 1:
                    time.sleep(delay)
            return results

        if not text_list:
            return []

        query_text = "\n".join(text_list)

        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': source_lang,
            'tl': 'en',
            'dt': 't',
            'q': query_text
        }

        url_with_params = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url_with_params)
        request.add_header('User-Agent', 'Mozilla/5.0')

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                translated_blob = ''.join([item[0] for item in result[0] if item[0]])
                translated_list = translated_blob.split('\n')

                if len(translated_list) == len(text_list):
                    return translated_list
                
                print(f"Batch translation mismatch: got {len(translated_list)} results for {len(text_list)} inputs. Falling back to individual translation.")
                return _fallback_individual()

        except Exception as e:
            print(f"Batch translation error: {e}. Falling back to individual translation.")
            return _fallback_individual()

    if isinstance(text, str):
        return _translate_single(text)

    elif isinstance(text, list):
        if not text:
            return []

        unique_bases_dict = {}
        for item in text:
            base, _ = _extract_suffix(item)
            if base and base.strip() and base not in unique_bases_dict:
                unique_bases_dict[base] = None
        
        unique_bases_list = list(unique_bases_dict.keys())

        if not unique_bases_list:
            return text

        translated_bases_list = _translate_batch(unique_bases_list)
        base_translation_map = dict(zip(unique_bases_list, translated_bases_list))

        results = []
        for item in text:
            if not item or not item.strip():
                results.append(item)
                continue

            base, suffix = _extract_suffix(item)
            translated_base = base_translation_map.get(base, base)
            if suffix:
                results.append(f"{translated_base}{suffix}")
            else:
                results.append(translated_base)

        return results

    else:
        raise TypeError("Input must be str or list of str")