# Golden Dataset（200 筆人工驗證）

供 3+3 郵遞區號查詢的人工驗證與回歸比對。

## 檔案

| 檔案 | 說明 |
|------|------|
| `golden_dataset_200.csv` | 主表（Excel 可開） |
| `golden_dataset_200.json` | 含分類統計的完整資料 |
| `build_log.txt` | 建置時查詢紀錄 |

重新建置：

```bash
cd backend
set PYTHONPATH=.
python ..\scripts\build_golden_dataset.py
```

## 欄位

| 欄位 | 說明 |
|------|------|
| `id` | G001–G200 |
| `category` | exact / normalize / needs_review / missing_city / missing_road / format_error / blank / house_number |
| `address` | 輸入地址 |
| `expected_*` | 金標（建議答案） |
| `actual_*` | 建置當下引擎實測 |
| `match_zip` / `match_status` | 金標與實測是否一致 |
| `verified` | 人工確認：`pending` → 改為 `pass` / `fail` |
| `notes` | 策展備註 |

## 組成

- **G001–G120**：全國縣市知名路段／地標（預期精確 6 碼）
- **G121–G160**：正規化變形（台→臺、舊鄉鎮市、全形／國字門牌、缺行政區等）
- **G161–G200**：異常與邊界（缺縣市、缺路段、空白、格式錯誤、無名牌等）

建置時會呼叫中華郵政 Web Service 填入建議 `expected_zipcode`；**仍須人工勾選 `verified`**，不可直接當成已驗證書。

## 人工驗證步驟

1. 用 Excel 開啟 `golden_dataset_200.csv`
2. 對每一列核對：
   - 正規化地址是否合理
   - 3+3 是否與中華郵政官網／信封一致
   - 異常列的 `expected_reason` 是否正確
3. 通過 → `verified=pass`；不符 → `verified=fail` 並在 `notes` 註明正確答案
4. 建議優先驗：臺北／新北／桃園／臺中／臺南／高雄（約 80 筆），再抽驗外縣市與異常列

## 自動評測

```bash
cd backend
set PYTHONPATH=.
python ..\scripts\eval_golden_dataset.py
```

輸出目錄：`samples/golden/eval/`

| 檔案 | 說明 |
|------|------|
| `eval_summary_latest.md` | 最新摘要（通過率／分類） |
| `eval_report_latest.json` | 完整逐筆結果 |
| `eval_failures_*.csv` | 失敗列明細 |

評分規則：
- **通過**：有金標的 `expected_zipcode` 與 `expected_status` 皆相符
- **zip%**：6 碼完全相符；另計前 3 碼相符率
- **reason%**：原因字串寬鬆比對（同義詞可過），不擋列通過
