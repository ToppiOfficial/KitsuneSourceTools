
import urllib.request
import urllib.parse
import json
import time
from typing import Union, List

def translate_to_english(text: Union[str, List[str]], source_lang: str = 'auto', batch_size: int = 50, delay: float = 0.5) -> Union[str, List[str]]:
    def _translate_single(text_str: str) -> str:
        if not text_str or not text_str.strip():
            return text_str
        
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': source_lang,
            'tl': 'en',
            'dt': 't',
            'q': text_str
        }
        
        url_with_params = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url_with_params)
        request.add_header('User-Agent', 'Mozilla/5.0')
        
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                translated = ''.join([item[0] for item in result[0] if item[0]])
                return translated
        except Exception as e:
            print(f"Translation error: {e}")
            return text_str
    
    def _translate_batch(text_list: List[str]) -> str:
        combined = '\n'.join(text_list)
        translated_combined = _translate_single(combined)
        return translated_combined.split('\n')
    
    if isinstance(text, str):
        return _translate_single(text)
    elif isinstance(text, list):
        results = []
        for i in range(0, len(text), batch_size):
            batch = text[i:i + batch_size]
            if len(batch) == 1:
                results.append(_translate_single(batch[0]))
            else:
                batch_results = _translate_batch(batch)
                results.extend(batch_results)
            if i + batch_size < len(text):
                time.sleep(delay)
        return results
    else:
        raise TypeError("Input must be str or list of str")