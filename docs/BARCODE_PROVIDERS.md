# 商业商品条码库从哪里找

> 商业商品库不是公开网站，而是按调用量/资源包收费的 API 服务。需要注册账号、实名认证、购买资源包，拿到 AppKey/AppCode 后才能查询。

## 一、可选服务商

| 服务商 | 适合场景 | 认证方式 | 国内商品覆盖 | 本项目接入状态 |
| --- | --- | --- | --- | --- |
| **ShowAPI（万维易源）66-22** | 国内零售商品、食品饮料 | `appKey` | 较好 | 已内置适配器，配置 `SHOWAPI_APP_KEY` 即用 |
| **聚合数据** 条码查询 | 国内商品 | `key` | 较好 | 需新增适配器，或走通用 `BARCODE_API_URL` |
| **阿里云市场** 商品条码查询类 API | 企业/开发者 | AppCode / 阿里云签名 | 取决于服务商 | 需按所选商家接口新增适配器 |
| **GS1 中国 / 中国物品编码中心** | 官方注册信息、合规核验 | 企业合作/授权 | 权威 | 通常不提供公开自助 Key，适合企业接入 |
| **Open Food Facts** | 国际食品、开放数据 | 无需 Key | 国内商品很弱 | **已作为免费兜底**，不是商业库 |
| **Barcode Lookup / UPCitemdb** | 海外商品 | API Key（部分有试用） | 海外较强、国内弱 | 可按需新增适配器 |

## 二、最快路径：ShowAPI

1. 打开 [ShowAPI 条码查询 66-22 文档](https://www.showapi.com/guides/barcode-quickstart-66)；
2. 注册/登录 ShowAPI，完成实名认证；
3. 在 API 市场找到 **条码查询（apiCode=66）**，购买 66-22 资源包或通用资源包；
4. 在控制台的 AppKey 管理页复制 AppKey；
5. 在项目根目录 `.env` 写入：

```env
BARCODE_PROVIDER=showapi
SHOWAPI_APP_KEY=你的AppKey
```

6. 重启后端，验证：

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_barcode.py 6925303773106
```

也可以在项目根目录运行交互脚本，输入时不会回显：

```powershell
.\backend\.venv\Scripts\python.exe scripts\configure_barcode.py
```

ShowAPI 成功查询通常按次扣资源包，失败是否扣费以服务商账单为准；本项目会把成功结果缓存 30 天，同一 GTIN 不重复请求。

## 三、其他服务商怎么接

### 方式 A：通用 JSON 代理（无需改代码）

如果你已有商业库/公司内部商品库，返回 JSON 至少包含 `name`，可配置：

```env
BARCODE_PROVIDER=generic
BARCODE_API_URL=https://your-api.example.com/product/{barcode}
BARCODE_API_KEY=xxx
BARCODE_API_KEY_HEADER=X-API-Key
```

支持字段：`name/title`、`brand`、`spec`、`manufacturer/manuName`、`category`、`goods_type`。

### 方式 B：新增专用适配器

聚合数据、阿里云市场商家的返回结构和鉴权方式不同（例如 `key` 查询参数、`APPCODE` 请求头），建议让开发者新增一个 provider 函数，而不是把 Key 拼进 URL。

## 四、免费兜底现状

没有商业 Key 时，项目会：

1. 查询 **Open Food Facts**；
2. 少量已核对的条码走 `backend/app/seed/barcode_catalog.py` 本地公开缓存；
3. 都没有则提示手动补名称。

免费库对国内商品覆盖有限。例如公开条码页显示 `6925303773106` 是“统一来一桶老坛酸菜牛肉面”，但 Open Food Facts 没有对应名称，所以免费模式查不到；这正是需要商业库的场景。

公开参考：[6925303773106 条码页](https://tiaoma.22tool.com/detail/f240ebd515df4618ac50f08a1ca92428)

## 五、安全与合规

- AppKey/AppCode 只放后端 `.env`，不要写进前端、截图或聊天记录；
- 不要把“成功查询”当成商品合规认证，商品信息仍应以包装和官方登记为准；
- 使用第三方数据要遵守服务商条款，不要用爬虫绕过鉴权；
- 生产环境建议用可撤销的测试 Key 先验证，再换正式 Key。
