"""检查商业条码库配置并查询一个条码（不会输出 AppKey 明文）。

用法：
    python scripts/check_barcode.py 6954767410388
    python scripts/check_barcode.py 6954767410388 --refresh-cache
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.services.shelf_life_service import lookup_barcode  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="商业条码库配置检查")
    parser.add_argument("barcode", help="13 位左右的商品条码")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        provider = str(app.config.get("BARCODE_PROVIDER") or "auto")
        showapi_set = bool(str(app.config.get("SHOWAPI_APP_KEY") or "").strip())
        generic_set = bool(str(app.config.get("BARCODE_API_URL") or "").strip())
        print(f"BARCODE_PROVIDER={provider}")
        print(f"SHOWAPI_APP_KEY={'已配置' if showapi_set else '未配置'}")
        print(f"BARCODE_API_URL={'已配置' if generic_set else '未配置'}")
        result = lookup_barcode(args.barcode)
        print(f"found={result.get('found')} source={result.get('source')}")
        if result.get("found"):
            print(f"name={result.get('name')}")
            print(f"brand={result.get('brand') or '-'} spec={result.get('spec') or '-'}")
            print(f"manufacturer={result.get('manufacturer') or '-'}")
            print(f"cached={result.get('cached')} shelf_life_days={((result.get('shelf_life') or {}).get('days'))}")
        else:
            print(f"message={result.get('message')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
