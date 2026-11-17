"""端到端接口冒烟测试（真实 HTTP 请求，可对本地或公网地址运行）。

用法：
    python scripts/api_smoke_test.py
    python scripts/api_smoke_test.py --base-url https://your-domain.com --username demo --password demo123456

它会依次验证：健康检查 → 未登录拦截 → 登录 → 上传 → OCR → 校正 → 分析
→ 记录详情 → 报告 → 图片读取 → 删除记录，并打印每一步的结果。
脚本会自行删除本次创建的记录，不会污染演示数据。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import requests
from login_helper import login as solve_login
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_LINES = [
    "醇香牌 原味发酵乳（接口测试样例）",
    "净含量：150g",
    "配料：生牛乳、白砂糖、乳清蛋白粉、保加利亚乳杆菌、嗜热链球菌",
    "营养成分表（每100g）",
    "能量 380kJ 5%    蛋白质 3.2g 5%",
    "脂肪 3.0g 5%     碳水化合物 12.5g 4%",
    "钠 55mg 3%",
    "生产日期：2026-01-15    保质期：21天",
    "贮存条件：2-6℃冷藏保存",
    "生产者：醇香乳业有限公司（测试样例）",
    "地址：示例省示例市示例区示例路 1 号",
    "产品标准号：GB 19302",
    "致敏物质提示：含有乳制品",
]

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def make_image() -> bytes:
    font_path = None
    for candidate in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        if Path(candidate).exists():
            font_path = candidate
            break
    font = ImageFont.truetype(font_path, 26) if font_path else ImageFont.load_default()
    title_font = ImageFont.truetype(font_path, 30) if font_path else font
    width, line_height = 940, 40
    image = Image.new("RGB", (width, 80 + line_height * len(SAMPLE_LINES) + 30), (253, 253, 251))
    draw = ImageDraw.Draw(image)
    draw.rectangle([6, 6, width - 7, image.height - 7], outline=(210, 210, 210), width=2)
    draw.text((28, 20), "接口测试自动生成的标签图片", fill=(190, 60, 60), font=title_font)
    y = 74
    for line in SAMPLE_LINES:
        draw.text((28, y), line, fill=(25, 25, 25), font=font)
        y += line_height
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="智膳 AI 接口冒烟测试")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="后端地址，例如 http://127.0.0.1:5000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo123456")
    parser.add_argument("--keep", action="store_true", help="保留测试创建的记录（默认删除）")
    parser.add_argument("--json-out", default="", help="把结果写入 JSON 文件")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api = f"{base}/api"
    session = requests.Session()
    print(f"\n== 目标：{base} ==\n")

    # 1. 健康检查
    resp = session.get(f"{api}/health", timeout=15)
    body = resp.json()
    check("GET /api/health 返回 200", resp.status_code == 200, f"HTTP {resp.status_code}")
    check("健康检查数据完整", bool(body.get("data", {}).get("checks")), json.dumps(body.get("data", {}).get("checks", {}), ensure_ascii=False))

    # 2. 未登录访问受保护接口
    resp = session.get(f"{api}/records", timeout=15)
    check("未登录访问 /api/records 被拒绝", resp.status_code == 401, f"HTTP {resp.status_code}")
    check("错误响应使用统一结构", resp.json().get("success") is False)

    # 3. 登录
    resp = solve_login(session, api, args.username, args.password, timeout=15)
    check("登录成功", resp.status_code == 200, f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:300])
        return 1
    token = resp.json()["data"]["token"]
    session.headers.update({"Authorization": f"Bearer {token}"})

    # 4. 基础读接口
    for path in ("/dashboard", "/records", "/knowledge", "/settings/status", "/auth/me"):
        resp = session.get(f"{api}{path}", timeout=20)
        check(f"GET /api{path}", resp.status_code == 200, f"HTTP {resp.status_code}")

    knowledge = session.get(f"{api}/knowledge", params={"query": "山梨酸钾"}, timeout=15).json()
    check("知识库关键词搜索有结果", knowledge["data"]["total"] >= 1, f"命中 {knowledge['data']['total']} 条")

    # 5. 上传
    image_bytes = make_image()
    resp = session.post(
        f"{api}/upload",
        files={"file": ("label_test.png", image_bytes, "image/png")},
        timeout=30,
    )
    upload = resp.json()
    check("POST /api/upload", resp.status_code == 201, upload.get("message", ""))
    if resp.status_code != 201:
        print(json.dumps(upload, ensure_ascii=False)[:500])
        return 1
    record_id = upload["data"]["record"]["id"]
    print(f"    记录 ID = {record_id}")

    # 6. OCR
    resp = session.post(f"{api}/ocr", json={"record_id": record_id}, timeout=180)
    ocr_body = resp.json()
    check("POST /api/ocr", resp.status_code == 200, ocr_body.get("message", ""))
    if resp.status_code != 200:
        print(json.dumps(ocr_body, ensure_ascii=False)[:500])
        return 1
    ocr = ocr_body["data"]
    fields = ocr["fields"]
    provider = ocr["provider"]
    print(f"    OCR 驱动：{provider['label']}（演示模式={provider['is_demo']}，耗时 {provider['duration_ms']}ms）")
    print(f"    食品名称：{fields.get('food_name')}")
    print(f"    配料表：{(fields.get('ingredients_text') or '')[:60]}")
    check("识别到配料表", bool((fields.get("ingredients_text") or "").strip()))
    check("识别到营养成分表", bool((fields.get("nutrition_text") or "").strip()))
    check("识别到生产日期", bool((fields.get("production_date") or "").strip()), fields.get("production_date", ""))

    # 7. 校正
    corrected = dict(fields)
    corrected["food_name"] = (fields.get("food_name") or "测试食品") + "（已人工校正）"
    resp = session.put(f"{api}/records/{record_id}/ocr", json={"fields": corrected}, timeout=20)
    check("PUT /api/records/<id>/ocr 保存校正", resp.status_code == 200, resp.json().get("message", ""))
    check("校正已写入 corrected_text", "已人工校正" in (resp.json()["data"]["ocr"]["corrected_text"] or ""))

    # 8. 分析
    resp = session.post(f"{api}/analyze", json={"record_id": record_id}, timeout=180)
    analyze = resp.json()
    check("POST /api/analyze", resp.status_code == 200, analyze.get("message", ""))
    if resp.status_code != 200:
        print(json.dumps(analyze, ensure_ascii=False)[:800])
        return 1
    result = analyze["data"]["result"]
    detail = analyze["data"]["detail"]
    print(f"    分析模式：{result['analysis_mode']}，整体核查：{result['overall']}，配料数：{result['ingredient_count']}")
    check("配料分析有结果", len(detail["ingredient"]["ingredients"]) >= 2, f"{len(detail['ingredient']['ingredients'])} 项")
    check("营养数据已解析", len([i for i in detail["nutrition"]["items"] if i["value"] is not None]) >= 3)
    check("核查结果条目完整", len(detail["check"]["items"]) >= 10, f"{len(detail['check']['items'])} 条")
    check("核查结论属于三档之一", result["overall"] in {"none_found", "needs_review", "suspected"})

    # 9. 记录详情与列表
    resp = session.get(f"{api}/records/{record_id}", timeout=20)
    check("GET /api/records/<id>", resp.status_code == 200)
    listing = session.get(f"{api}/records", params={"query": "测试", "page": 1, "per_page": 5}, timeout=20).json()
    listing_data = listing.get("data") or {}
    check(
        "历史记录分页查询",
        "items" in listing_data and listing_data.get("page") == 1,
        f"共 {listing_data.get('total', '?')} 条",
    )

    # 10. 报告
    resp = session.get(f"{api}/reports/{record_id}", timeout=30)
    report = resp.json()
    check("GET /api/reports/<id>", resp.status_code == 200, report.get("message", ""))
    if resp.status_code == 200:
        data = report["data"]
        check("报告带编号与生成时间", bool(data["report"]["report_no"]) and bool(data["report"]["generated_at"]))
        check("报告包含免责声明", bool(data["meta"].get("disclaimer")))
        check("报告包含核查依据来源", len(data["rule_sources"]) >= 1, f"{len(data['rule_sources'])} 个来源")

    # 11. 图片读取
    resp = session.get(f"{api}/records/{record_id}/image", timeout=20)
    check("GET /api/records/<id>/image", resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/"))

    # 12. 越权检查：另一个不存在的 ID 应返回 404
    resp = session.get(f"{api}/records/999999", timeout=15)
    check("访问不存在记录返回 404", resp.status_code == 404, f"HTTP {resp.status_code}")

    # 13. 清理
    if not args.keep:
        resp = session.delete(f"{api}/records/{record_id}", timeout=20)
        check("DELETE /api/records/<id>", resp.status_code == 200)
        resp = session.get(f"{api}/records/{record_id}", timeout=15)
        check("删除后记录不可访问", resp.status_code == 404, f"HTTP {resp.status_code}")

    print(f"\n结果：通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("失败项：" + "；".join(FAILED))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"passed": PASSED, "failed": FAILED, "base_url": base}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
