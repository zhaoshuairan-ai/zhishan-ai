"""本地公开条码缓存（演示用，非商业库）。

仅收录已从公开条码查询页核对的少量条码，用于无商业 Key 时演示扫码流程。
生产环境请配置 SHOWAPI_APP_KEY 或 BARCODE_API_URL，不要把本文件当作完整商品库。
数据来源：https://tiaoma.22tool.com/detail/329b74c304364e2eaa3aa362d6223a39
"""

LOCAL_BARCODE_CATALOG = {
    "6954767410388": {
        "name": "可口可乐汽水",
        "brand": "可口可乐",
        "spec": "330毫升",
        "manufacturer": "中粮可口可乐饮料(中国)投资有限公司",
        "category": "other",
        "source_url": "https://tiaoma.22tool.com/detail/329b74c304364e2eaa3aa362d6223a39",
        "note": "本地公开数据缓存，非商业条码库结果",
    }
}

CATALOG_VERSION = "local-2026.10"
