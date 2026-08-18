# 台灣 3+3 郵遞區號查詢（MVP）

雲端 SaaS 雛形：單筆查詢 + 檔案批次 ETL。

## 能力

- **自動正規化**：台/臺、簡稱、全半形、號之格式、去開頭郵遞區號等
- **全國地址**：本地路段快速命中；未命中改打中華郵政 `GetZipAddress` / `GetZipCode`
- **完整 6 碼**：成功時輸出完整 3+3；結果含「正規化地址」
- **批次 ETL**：`.csv` / `.xlsx` / `.xls` / `.ods`（最多 1000 筆），輸出同格式

## 啟動

```powershell
cd c:\Users\sport\postal_code\backend
c:\Users\sport\postal_code\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

瀏覽 http://127.0.0.1:8000/

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `POST_WS_ENABLED` | `1` | 設 `0` 可關閉郵政 WS（僅本地） |
| `POST_WS_URL` | 官方 asmx | Web Service 位址 |
| `POST_WS_TIMEOUT` | `8` | 秒 |

## 查詢流程

1. **正規化**地址（舊鄉鎮市、全形／國字數字等）  
2. **大宗郵件專用郵遞區號**（`backend/data/bulk_zipcodes.json`，優先）  
3. 中華郵政 Web Service  
4. 本地路段庫  
5. 僅在都失敗時，退回行政區前 3 碼 + `000`

### 大宗專用表格式

```json
[
  {"name": "客戶名稱可空", "address": "高雄市鳳山區中山路157號", "zip6": "830888", "note": "說明"}
]
```

比對鍵：正規化後的地址；若有填 `name` 則「名稱+地址」優先於「僅地址」。

## 公開部署

### 方式 A：Docker（本機映像）

```powershell
cd c:\Users\sport\Postal_code
docker build -t tw-zipcode-saas .
docker run --rm -p 8000:8000 -e PORT=8000 tw-zipcode-saas
```

### 方式 B：Render（免費公開網址）

1. 將專案推上 GitHub
2. 到 https://render.com 建立 Web Service，選此 repo、Runtime=Docker
3. 或使用已附的 `render.yaml`

### 方式 C：Fly.io

```powershell
# 安裝後
fly auth login
fly launch --name tw-zipcode-saas --region nrt --no-deploy
fly deploy
```

環境變數：`POST_WS_ENABLED=1`（預設開啟中華郵政查詢）

> 中華郵政 Web Service 正式長期介接建議依官方申請流程辦理；本專案以公開 WSDL 介面實作查詢與快取。
