"""建立 200 筆人工驗證 Golden Dataset。

用法（在 backend 目錄）：
  set PYTHONPATH=.
  python ..\\scripts\\build_golden_dataset.py

輸出：
  samples/golden/golden_dataset_200.csv
  samples/golden/golden_dataset_200.json
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.zipcode.engine import lookup_address  # noqa: E402


OUT_DIR = ROOT / "samples" / "golden"


def _case(
    cid: str,
    category: str,
    address: str,
    *,
    name: str = "",
    notes: str = "",
    seed_mode: str = "post_ws",
    expected_zipcode: str = "",
    expected_status: str = "",
    expected_reason: str = "",
) -> dict:
    return {
        "id": cid,
        "category": category,
        "name": name or f"案例{cid}",
        "address": address,
        "notes": notes,
        "seed_mode": seed_mode,
        "expected_zipcode": expected_zipcode,
        "expected_status": expected_status,
        "expected_reason": expected_reason,
    }


def build_seeds() -> list[dict]:
    """人工策展 200 筆：地理覆蓋 + 正規化 + 異常。"""
    seeds: list[dict] = []

    # --- A. 精確查詢（知名地標／常用路段）約 120 ---
    landmarks = [
        ("臺北市大安區愛國東路216號", "大安森林公園附近／郵政常見測資"),
        ("臺北市信義區信義路五段7號", "台北101"),
        ("臺北市信義區松仁路58號", "信義商圈"),
        ("臺北市中正區重慶南路一段122號", "總統府周邊"),
        ("臺北市中正區忠孝東路一段9號", "台北車站周邊"),
        ("臺北市中山區南京東路二段100號", "南京東路商圈"),
        ("臺北市中山區中山北路二段48號", "中山北路"),
        ("臺北市松山區南京東路四段133號", "松山南京東"),
        ("臺北市大安區敦化南路一段245號", "敦化南路"),
        ("臺北市大安區忠孝東路四段45號", "忠孝東路四段"),
        ("臺北市大安區復興南路一段390號", "復興南路"),
        ("臺北市萬華區西園路一段136號", "西門町周邊"),
        ("臺北市文山區木柵路三段220號", "文山木柵"),
        ("臺北市南港區經貿二路1號", "南港展覽館周邊"),
        ("臺北市內湖區成功路四段188號", "內湖成功路"),
        ("臺北市士林區中正路455號", "士林"),
        ("臺北市北投區中央北路一段168號", "北投"),
        ("臺北市大同區承德路三段230號", "大同承德路"),
        ("新北市板橋區文化路一段188號", "板橋文化路"),
        ("新北市板橋區縣民大道二段7號", "板橋車站周邊"),
        ("新北市中和區景平路488號", "中和"),
        ("新北市永和區中正路100號", "永和"),
        ("新北市新莊區中正路100號", "新莊"),
        ("新北市三重區重新路四段50號", "三重"),
        ("新北市新店區北新路三段90號", "新店"),
        ("新北市汐止區大同路一段200號", "汐止"),
        ("新北市淡水區中正東路一段10號", "淡水"),
        ("新北市林口區文化一路100號", "林口"),
        ("新北市蘆洲區三民路100號", "蘆洲"),
        ("新北市土城區中央路二段100號", "土城"),
        ("桃園市桃園區中正路100號", "桃園中正路"),
        ("桃園市中壢區中正路100號", "中壢"),
        ("桃園市平鎮區環南路100號", "平鎮"),
        ("桃園市蘆竹區南崁路100號", "蘆竹南崁"),
        ("桃園市龜山區復興一路100號", "龜山"),
        ("桃園市八德區介壽路100號", "八德"),
        ("桃園市楊梅區中山北路一段100號", "楊梅"),
        ("桃園市大園區中正東路100號", "大園"),
        ("臺中市西屯區臺灣大道三段99號", "台中臺灣大道"),
        ("臺中市西屯區文心路三段100號", "西屯文心"),
        ("臺中市北屯區崇德路二段200號", "北屯崇德"),
        ("臺中市北區一中街100號", "一中商圈"),
        ("臺中市中區中山路100號", "台中中區"),
        ("臺中市南屯區五權西路二段100號", "南屯"),
        ("臺中市東區復興路四段100號", "台中東區"),
        ("臺中市南區復興路一段100號", "台中南區"),
        ("臺中市西區公益路100號", "西區公益路"),
        ("臺中市豐原區中正路100號", "豐原"),
        ("臺中市大里區中興路二段100號", "大里"),
        ("臺中市太平區中山路一段100號", "太平"),
        ("臺南市東區大學路1號", "成大周邊"),
        ("臺南市中西區中正路100號", "台南中西區"),
        ("臺南市北區西門路三段100號", "台南北區"),
        ("臺南市安平區安平路100號", "安平"),
        ("臺南市永康區中華路100號", "永康"),
        ("臺南市新營區中正路100號", "新營"),
        ("臺南市仁德區中山路100號", "仁德"),
        ("高雄市苓雅區四維三路2號", "高雄市政府周邊"),
        ("高雄市前金區中正四路100號", "前金"),
        ("高雄市左營區博愛二路777號", "左營博愛"),
        ("高雄市鼓山區臨海二路100號", "鼓山"),
        ("高雄市三民區建國三路100號", "三民"),
        ("高雄市新興區中山一路100號", "新興"),
        ("高雄市前鎮區中山二路100號", "前鎮"),
        ("高雄市鳳山區光復路一段100號", "鳳山"),
        ("高雄市楠梓區高楠公路100號", "楠梓"),
        ("高雄市小港區中山路100號", "小港"),
        ("基隆市中正區中正路100號", "基隆中正"),
        ("基隆市仁愛區仁一路100號", "基隆仁愛"),
        ("新竹市東區光復路二段101號", "清大／光復路"),
        ("新竹市東區中華路二段100號", "新竹中華路"),
        ("新竹市北區中正路100號", "新竹北區"),
        ("新竹縣竹北市光明六路100號", "竹北"),
        ("新竹縣竹東鎮長春路三段100號", "竹東"),
        ("苗栗縣苗栗市中正路100號", "苗栗"),
        ("苗栗縣竹南鎮中正路100號", "竹南"),
        ("苗栗縣頭份市中正路100號", "頭份"),
        ("彰化縣彰化市中山路一段1號", "彰化"),
        ("彰化縣員林市中山路一段100號", "員林"),
        ("彰化縣鹿港鎮中山路100號", "鹿港"),
        ("南投縣南投市中興路100號", "南投"),
        ("南投縣埔里鎮中山路一段100號", "埔里"),
        ("雲林縣斗六市中山路100號", "斗六"),
        ("雲林縣虎尾鎮林森路一段100號", "虎尾"),
        ("嘉義市西區中山路100號", "嘉義西區"),
        ("嘉義市東區中山路100號", "嘉義東區"),
        ("嘉義縣太保市中正路100號", "太保"),
        ("嘉義縣朴子市山通路100號", "朴子"),
        ("屏東縣屏東市中正路100號", "屏東"),
        ("屏東縣潮州鎮中山路100號", "潮州"),
        ("宜蘭縣宜蘭市中山路二段100號", "宜蘭"),
        ("宜蘭縣羅東鎮中正路100號", "羅東"),
        ("花蓮縣花蓮市中山路17號", "花蓮"),
        ("花蓮縣吉安鄉中山路一段100號", "吉安"),
        ("臺東縣臺東市中山路100號", "臺東"),
        ("澎湖縣馬公市中正路100號", "馬公"),
        ("金門縣金城鎮民權路100號", "金城"),
        ("連江縣南竿鄉介壽村100號", "南竿"),
        ("臺北市大安區仁愛路四段27號", "仁愛路四段"),
        ("臺北市信義區基隆路一段200號", "基隆路一段"),
        ("臺北市中正區羅斯福路一段1號", "羅斯福路一段"),
        ("新北市板橋區民生路一段100號", "板橋民生"),
        ("新北市新莊區新泰路100號", "新莊新泰"),
        ("桃園市中壢區元化路100號", "中壢元化"),
        ("臺中市西屯區河南路二段100號", "河南路二段"),
        ("臺中市北屯區進化路100號", "北屯進化"),
        ("臺南市東區崇學路100號", "東區崇學"),
        ("高雄市苓雅區光華一路100號", "苓雅光華"),
        ("高雄市左營區自由二路100號", "左營自由"),
        ("新竹市東區中央路100號", "新竹中央路"),
        ("基隆市中山區中山一路100號", "基隆中山"),
        ("嘉義市西區民生北路100號", "嘉義民生北"),
        ("彰化縣和美鎮道周路100號", "和美"),
        ("雲林縣北港鎮中山路100號", "北港"),
        ("屏東縣東港鎮光復路一段100號", "東港"),
        ("宜蘭縣礁溪鄉中山路一段100號", "礁溪"),
        ("花蓮縣壽豐鄉大學路二段100號", "壽豐東華周邊"),
        ("臺東縣成功鎮中山路100號", "成功"),
        ("苗栗縣通霄鎮中山路100號", "通霄中山路"),
        ("臺中市北區大雅路100號", "北區大雅路"),
        ("新北市樹林區中山路一段100號", "樹林"),
        ("新北市鶯歌區中正一路100號", "鶯歌"),
        ("桃園市龍潭區中正路100號", "龍潭"),
        ("高雄市岡山區岡山路100號", "岡山"),
        ("高雄市路竹區中山路100號", "路竹"),
        ("臺南市善化區中山路100號", "善化"),
        ("臺南市佳里區光復路100號", "佳里"),
    ]
    landmarks = landmarks[:120]
    for i, (addr, note) in enumerate(landmarks, start=1):
        seeds.append(
            _case(
                f"G{i:03d}",
                "exact",
                addr,
                notes=note,
                seed_mode="post_ws",
            )
        )

    # --- B. 正規化變形（同一地點不同寫法）約 40 ---
    normalize_pairs = [
        ("台北市大安區愛國東路216號", "台→臺"),
        ("台北市信義區信義路五段7號", "台→臺"),
        ("台中市西屯區台灣大道三段99號", "台中／台灣大道正規化"),
        ("台南市東區大學路1號", "台→臺"),
        ("鳳山市光復路一段100號", "舊鄉鎮市→高雄市鳳山區"),
        ("板橋市文化路一段188號", "舊板橋市→新北市板橋區"),
        ("中壢市中正路100號", "舊中壢市→桃園市中壢區"),
        ("豐原市中正路100號", "舊豐原市→臺中市豐原區"),
        ("永康市中華路100號", "舊永康市→臺南市永康區"),
        ("三重市重新路四段50號", "舊三重市→新北市三重區"),
        ("臺北市大安區愛國東路２１６號", "全形數字"),
        ("臺北市大安區愛國東路二一六號", "國字門牌"),
        ("臺北市大安區愛國東路216-1號", "門牌之號格式"),
        ("臺北市大安區敦化南路一段245號12F", "樓層 F→樓"),
        ("北市大安區愛國東路216號", "縣市簡稱北市"),
        ("高市苓雅區四維三路2號", "縣市簡稱高市"),
        ("中市西屯區臺灣大道三段99號", "縣市簡稱中市"),
        ("桃園縣中壢市中正路100號", "舊縣名＋鄉鎮市"),
        ("高雄縣鳳山市光復路一段100號", "舊高雄縣鳳山市"),
        ("臺北縣板橋市文化路一段188號", "舊臺北縣板橋市"),
        ("台北縣中和市景平路488號", "舊台北縣中和市"),
        ("台中縣豐原市中正路100號", "舊台中縣豐原市"),
        ("台南縣永康市中華路100號", "舊台南縣永康市"),
        ("新竹市中華路二段100號", "缺行政區（應推論東區）"),
        ("嘉義市中山路100號", "缺行政區（西／東區可能歧義，記結果）"),
        ("基隆市中山一路100號", "缺行政區（應推論）"),
        ("臺北市大安區愛國東路216號　", "尾端空白"),
        (" 臺北市大安區愛國東路216號", "前端空白"),
        ("臺北市大安區愛國東路216號。", "句點"),
        ("臺北市大安區（愛國東路）216號", "括號"),
        ("臺北市大安區愛國東路第216號", "第N號"),
        ("臺北市信義區市府路1號", "市府路"),
        ("新北市板橋區縣民大道一段1號", "縣民大道"),
        ("桃園市桃園區縣府路1號", "縣府路"),
        ("臺中市西屯區臺灣大道四段100號", "臺灣大道四段"),
        ("高雄市前鎮區成功二路100號", "成功二路"),
        ("臺南市中西區民權路二段100號", "民權路二段"),
        ("新竹縣竹北市莊敬東路100號", "竹北莊敬東路"),
        ("彰化縣彰化市曉陽路100號", "曉陽路"),
        ("花蓮縣花蓮市中正路100號", "花蓮中正路"),
    ]
    base = len(seeds)
    for j, (addr, note) in enumerate(normalize_pairs, start=1):
        seeds.append(
            _case(
                f"G{base + j:03d}",
                "normalize",
                addr,
                notes=f"正規化：{note}",
                seed_mode="post_ws",
            )
        )

    # --- C. 需確認／異常（人工預期）約 40 ---
    manual = [
        ("G161", "needs_review", "臺北市大安區某未知小路1號", "查無對應路段→可能行政區備援", "district", "查無對應路段"),
        ("G162", "needs_review", "臺中市北區虛構大道9999號", "虛構路名", "district", "查無對應路段"),
        ("G163", "missing_city", "光復路157號", "缺縣市", "not_found", "缺少縣市"),
        ("G164", "missing_city", "中正路100號", "缺縣市", "not_found", "缺少縣市"),
        ("G165", "missing_road", "臺北市大安區", "缺路段", "district", "缺少路段"),
        ("G166", "missing_road", "新北市板橋區", "缺路段", "district", "缺少路段"),
        ("G167", "missing_road", "高雄市苓雅區", "缺路段", "district", "缺少路段"),
        ("G168", "format_error", "這不是地址@@@", "格式錯誤", "not_found", "地址格式錯誤"),
        ("G169", "format_error", "!!!!!!", "格式錯誤", "not_found", "地址格式錯誤"),
        ("G170", "format_error", "12345", "純數字", "not_found", "地址格式錯誤"),
        ("G171", "blank", "", "空白地址", "not_found", "地址格式錯誤"),
        ("G172", "blank", "   ", "空白地址", "not_found", "地址格式錯誤"),
        ("G173", "house_number", "臺北市大安區愛國東路", "有路無名牌", "district", "門牌無法判斷"),
        ("G174", "house_number", "臺北市信義區信義路五段", "有路無名牌", "district", "門牌無法判斷"),
        ("G175", "house_number", "新北市板橋區文化路一段", "有路無名牌", "district", "門牌無法判斷"),
        ("G176", "exact", "臺北市大安區忠孝東路四段45號之1", "之號門牌", "", ""),
        ("G177", "exact", "臺北市中山區民生東路三段100巷10號", "巷弄", "", ""),
        ("G178", "exact", "臺北市大安區和平東路二段96巷15弄5號", "巷弄", "", ""),
        ("G179", "exact", "新北市中和區景安路100號", "景安路", "", ""),
        ("G180", "exact", "新北市新店區中正路100號", "新店中正", "", ""),
        ("G181", "exact", "桃園市中壢區中央西路一段100號", "中央西路", "", ""),
        ("G182", "exact", "臺中市南屯區文心南路100號", "文心南路", "", ""),
        ("G183", "exact", "臺南市安南區安中路一段100號", "安中路", "", ""),
        ("G184", "exact", "高雄市鳳山區自由路100號", "鳳山自由路", "", ""),
        ("G185", "exact", "基隆市暖暖區暖暖街100號", "暖暖", "", ""),
        ("G186", "exact", "新竹市香山區中華路五段100號", "香山", "", ""),
        ("G187", "exact", "嘉義市東區垂楊路100號", "垂楊路", "", ""),
        ("G188", "exact", "彰化縣彰化市辭修路100號", "辭修路", "", ""),
        ("G189", "exact", "南投縣草屯鎮中正路100號", "草屯", "", ""),
        ("G190", "exact", "雲林縣斗南鎮中山路100號", "斗南", "", ""),
        ("G191", "exact", "屏東縣恆春鎮中山路100號", "恆春", "", ""),
        ("G192", "exact", "宜蘭縣頭城鎮青雲路一段100號", "頭城", "", ""),
        ("G193", "exact", "花蓮縣玉里鎮中山路一段100號", "玉里", "", ""),
        ("G194", "exact", "臺東縣關山鎮中正路100號", "關山", "", ""),
        ("G195", "exact", "澎湖縣湖西鄉中正路100號", "湖西", "", ""),
        ("G196", "normalize", "台北市大安區忠孝東路4段45號", "段用阿拉伯數字", "", ""),
        ("G197", "normalize", "臺北市大安區忠孝東路４段４５號", "全形段與門牌", "", ""),
        ("G198", "needs_review", "臺北市大安區", "僅行政區", "district", "缺少路段"),
        ("G199", "missing_city", "愛國東路216號", "缺縣市行政區", "not_found", "缺少縣市"),
        ("G200", "format_error", "N/A", "無效字串", "not_found", "地址格式錯誤"),
    ]
    for cid, category, address, notes, estatus, ereason in manual:
        mode = "manual" if estatus else "post_ws"
        seeds.append(
            _case(
                cid,
                category,
                address,
                notes=notes,
                seed_mode=mode,
                expected_status=estatus,
                expected_reason=ereason,
            )
        )

    # 保險：剛好 200
    if len(seeds) != 200:
        raise RuntimeError(f"預期 200 筆，實際 {len(seeds)} 筆")
    return seeds


def enrich(seeds: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for i, seed in enumerate(seeds, start=1):
        row = dict(seed)
        addr = (seed["address"] or "").strip()
        mode = seed["seed_mode"]

        if mode == "manual" and not addr:
            row.update(
                {
                    "actual_zipcode": "",
                    "actual_status": "not_found",
                    "actual_reason": "地址格式錯誤",
                    "actual_normalized": "",
                    "actual_source": "none",
                    "match_zip": "",
                    "match_status": "pending_manual",
                    "verified": "pending",
                }
            )
            # blank expected
            if not row["expected_status"]:
                row["expected_status"] = "not_found"
            if not row["expected_reason"]:
                row["expected_reason"] = "地址格式錯誤"
            rows.append(row)
            continue

        # 查詢引擎（含郵政）以產生建議答案；人工仍需勾選 verified
        try:
            result = lookup_address(addr, use_post_ws=True) if addr else None
        except Exception as exc:  # noqa: BLE001
            row.update(
                {
                    "actual_zipcode": "",
                    "actual_status": "not_found",
                    "actual_reason": f"API錯誤（{exc}）",
                    "actual_normalized": "",
                    "actual_source": "none",
                    "match_zip": "",
                    "match_status": "error",
                    "verified": "pending",
                }
            )
            rows.append(row)
            print(f"[{i}/200] {seed['id']} ERROR {exc}", flush=True)
            continue

        if result is None:
            result_zip = ""
            result_status = "not_found"
            result_reason = "地址格式錯誤"
            result_norm = ""
            result_source = "none"
        else:
            result_zip = result.zipcode or ""
            result_status = result.status
            result_reason = result.reason or ""
            result_norm = result.normalized or ""
            result_source = result.source or ""

        if mode == "post_ws":
            # 以本次官方／引擎結果作為建議金標，待人工確認
            if not row["expected_zipcode"]:
                row["expected_zipcode"] = result_zip
            if not row["expected_status"]:
                row["expected_status"] = result_status
            if not row["expected_reason"]:
                row["expected_reason"] = result_reason

        match_zip = (
            "Y"
            if row["expected_zipcode"] and row["expected_zipcode"] == result_zip
            else ("N" if row["expected_zipcode"] else "")
        )
        match_status = (
            "Y"
            if row["expected_status"] and row["expected_status"] == result_status
            else ("N" if row["expected_status"] else "")
        )

        row.update(
            {
                "actual_zipcode": result_zip,
                "actual_status": result_status,
                "actual_reason": result_reason,
                "actual_normalized": result_norm,
                "actual_source": result_source,
                "match_zip": match_zip,
                "match_status": match_status,
                "verified": "pending",
            }
        )
        rows.append(row)
        print(
            f"[{i}/200] {seed['id']} {result_status} {result_zip or '—'} | {addr[:28]}",
            flush=True,
        )
        # 輕微節流，避免打爆郵政 WS
        if i % 10 == 0:
            time.sleep(0.4)

    return rows


def write_outputs(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "golden_dataset_200.csv"
    json_path = OUT_DIR / "golden_dataset_200.json"

    fields = [
        "id",
        "category",
        "name",
        "address",
        "expected_zipcode",
        "expected_status",
        "expected_reason",
        "actual_zipcode",
        "actual_status",
        "actual_reason",
        "actual_normalized",
        "actual_source",
        "match_zip",
        "match_status",
        "verified",
        "notes",
        "seed_mode",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    meta = {
        "title": "TW 3+3 Golden Dataset",
        "count": len(rows),
        "verified_pending": sum(1 for r in rows if r.get("verified") == "pending"),
        "categories": {},
        "rows": rows,
    }
    for row in rows:
        meta["categories"][row["category"]] = meta["categories"].get(row["category"], 0) + 1

    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")


def main() -> None:
    seeds = build_seeds()
    rows = enrich(seeds)
    write_outputs(rows)


if __name__ == "__main__":
    main()
