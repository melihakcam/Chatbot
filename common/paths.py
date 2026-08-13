"""Proje yolları ve büyük dosyaların nereye ineceği.

NEDEN VAR:
    HuggingFace modelleri varsayılan olarak C:\\Users\\<kullanici>\\.cache\\huggingface
    altına iner. multilingual-e5-small ~500 MB, ileride başka model denenirse
    birkaç GB'ı bulur. Bu projede büyük dosyalar D: sürücüsünde tutuluyor.

    setup_model_cache() sentence_transformers/transformers IMPORT EDİLMEDEN ÖNCE
    çağrılmalı — kütüphaneler cache yolunu import anında okuyor, sonradan
    değiştirmek işe yaramıyor.
"""

import os
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent

DATA = PROJE_KOK / "data"
SAMPLE_PAGES = DATA / "sample" / "pages.sample.jsonl"
RAW_PAGES = DATA / "raw" / "pages.jsonl"
INDEX_DIR = DATA / "index"
LOGS_DIR = DATA / "logs"

# Model ağırlıkları (büyük dosyalar) — D: sürücüsünde, .gitignore kapsamında.
MODEL_CACHE = DATA / "models"


def setup_model_cache() -> Path:
    """HuggingFace cache'ini D:'ye yönlendirir. Import'lardan ÖNCE çağrılmalı."""
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(MODEL_CACHE))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(MODEL_CACHE))
    return MODEL_CACHE
