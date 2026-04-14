from __future__ import annotations

import os
from typing import List

# Có thể đặt thêm biến môi trường BOTR_ADMINS="id1,id2,id3"
_raw = os.getenv("BOTR_ADMINS", "").strip()

if _raw:
    ADMINS: List[str] = [x.strip() for x in _raw.split(",") if x.strip()]
else:
    ADMINS = [
        "1257617565409083427"  # Thay bằng ID của bạn
    ]

print("Loaded data admin has success")
