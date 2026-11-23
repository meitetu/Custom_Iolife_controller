

# IoLIFE Custom Controller

ToshibaのIotエアコン等の制御に使うIoLIFE（Toshiba）アプリのAPIの仕様を元にした、研究・検証用のPython製ツールです。  
`main.py` 1本でログイン、機器一覧、透過送信、AC (`0xAC`) の最小クエリ/電源制御を行えます。
`custom_components/iolife/` に Home Assistant 用のカスタム統合も同梱しています。

> [!CAUTION]
> **免責事項・利用上の注意**
> * 本スクリプトは東芝（Toshiba）が公式に提供しているAPIではなく、リバースエンジニアリング等に基づいた研究・検証用のコードです。
> * サービス側の仕様変更により、予告なく動作しなくなる可能性があります。
> * 本ツールの利用によって生じた損害やトラブルについて、作者は一切の責任を負いません。教育的利用に留めてください（Education purpose only）

## 対応機能
- `user/login/id/get` + `user/login` でログイン
- `session.json` へセッション保存
- `appliance/user/home/page/list/info` で機器一覧取得
- 任意エンドポイントへの署名付きPOST (`call`)
- `appliance/transparent/send` 送信 (`transparent`)
- AC向け最小クエリ送信 (`ac-query`)
- AC電源ON/OFF送信 (`ac-power`)
- ACモード/温度/風量の制御送信 (`ac-control`、複数設定を1フレームで送る `--batch`、`--decode` で応答を人間可読に)
- Home Assistant カスタム統合 (`custom_components/iolife/`)

## Home Assistant 統合

`custom_components/iolife/` に Home Assistant 用のカスタム統合があります。
実際に動作を確認できた制御だけを実装しています。

| 機能 | 対応 |
|------|------|
| 電源 ON/OFF | OK |
| 運転モード (自動/冷房/除湿/暖房/送風) | OK |
| 設定温度 (16.0〜30.0℃、0.5℃刻み) | OK |
| 風量 (自動/強/中/弱/おやすみ) | OK |
| 上下・左右スイング | OK |
| 室温・室外温度・湿度・eco・空清 | 参照のみ |
| タイマー、画面表示、ビープー音 | 非対応 (実機が無視するため) |

### 配置手順

#### HACS から入れる場合

1. HACS → 右上の「︙」→ **カスタムリポジトリ**
2. リポジトリに `meitetu/Custom_Iolife_controller`、カテゴリに **統合 (Integration)** を選んで追加
3. HACS の画面から **Toshiba IoLIFE** をダウンロード
4. HA を再起動

#### 手動で入れる場合

1. `custom_components/iolife` を HA の `/config/custom_components/iolife` にコピー
2. HA を再起動

#### 共通の設定

3. 「設定 → デバイスとサービス → 統合を追加」で **Toshiba IoLIFE** を選ぶ
4. IoLIFE アプリと同じメールアドレスとパスワードを入力
5. エアコンごとに `climate` エンティティが作られる

`iolife` フォルダがそのまま `/config/custom_components/iolife` になるように
配置してください。

> [!NOTE]
> `pycryptodome` が必要です。HA OS では `manifest.json` の
> `requirements` から自動インストールされます。

### 未検証の部分

- ログイン処理はこのリポジトリの `main.py` と同じ実装ですが、HA 統合側から
  のログインは実機で未確認です (ローカル検証は `session.json` の再利用と
  プロトコル単体テストのみ)
- 2 台目以降のエアコンは未検証 (1 台目と同じ `0xAC` なら同じ扱いになる想定)

## 動作環境
- Python 3.10+
- `pycryptodome`


## クイックスタート
### 1) ログイン
```bash
python3 main.py login --account your_email@example.com --password 'your_password'
```

`main.py` と同じディレクトリに `session.json` を保存します。

### 2) 機器一覧確認
```bash
python3 main.py devices
```

### 3) AC状態クエリ
```bash
python3 main.py ac-query --appliance-id 1234567890123 --decode-reply --verbose

# 応答を人間可読にデコード
python3 main.py ac-query --appliance-id 1234567890123 --decode

# 全プロパティを1回のクエリで取得
python3 main.py ac-query --appliance-id 1234567890123 --query-type all_props --decode
```

### 4) エアコンの電源ON
```bash
python3 main.py ac-power --appliance-id 1234567890123 --state on --decode-reply --verbose
```

### 5) モード/温度/風量の制御
```bash
# 1設定ずつ送る
python3 main.py ac-control --appliance-id 1234567890123 --mode cool
python3 main.py ac-control --appliance-id 1234567890123 --temperature 24.5
python3 main.py ac-control --appliance-id 1234567890123 --fan strong

# 複数設定を1フレームで送る（エアコンのビープ音が1回で済む）
python3 main.py ac-control --appliance-id 1234567890123 --mode cool --temperature 24 --fan strong --batch
```

> [!NOTE]
> 制御フレームを送るたびにエアコンがビープ音を鳴らします。複数項目を変えるときは `--batch` を使ってください。


## コマンド一覧
### `login`
ログインして `session.json` を更新します。

```bash
python3 main.py login --account <email> --password <password>
```

### `devices`
機器一覧を取得します。

```bash
python3 main.py devices
```

### `call`
任意エンドポイントへ署名付きPOSTを実行します。

```bash
python3 main.py call --endpoint user/info/get --use-saved-session
python3 main.py call --endpoint user/email/info/get --param foo=bar --use-saved-session
```

### `transparent`
`appliance/transparent/send` の低レイヤ送信です。

```bash
# すでに暗号化済み order を送る
python3 main.py transparent --appliance-id 1234567890123 --order '<encrypted_order>'

# payload hex から datagram + AES暗号化して送る
python3 main.py transparent --appliance-id 1234567890123 --payload-hex '55AACC33...' --decode-reply --verbose
```

### `ac-query`
AC (`0xAC`) 向けのクエリを生成して送信します。

```bash
# 全状態クエリ
python3 main.py ac-query --appliance-id 1234567890123 --decode-reply --verbose

# プロパティ指定クエリ（例: power）
python3 main.py ac-query --appliance-id 1234567890123 --query-type power --decode-reply

# 送信せず payload hex のみ確認
python3 main.py ac-query --appliance-id 1234567890123 --print-payload
```

主な `--query-type` 例:
- `power`
- `mode`
- `temperature`
- `indoor_temperature`
- `outdoor_temperature`
- `wind_speed`
- `eco`
- `purifier`
- `error_code_query`
- `all`（既定）

### `ac-power`
AC電源ON/OFFを送信します。

```bash
python3 main.py ac-power --appliance-id 1234567890123 --state on --decode-reply --verbose
python3 main.py ac-power --appliance-id 1234567890123 --state off --decode-reply --verbose
```

### `ac-control`
ACのモード・温度・風量を送信します。複数指定した場合、既定では1設定ずつ
(その都度ビープ音)送信します。`--batch` を付けると1つの複数プロパティ
フレームにまとめて送るので、ビープ音は1回だけです。

```bash
python3 main.py ac-control --appliance-id 1234567890123 --mode cool
python3 main.py ac-control --appliance-id 1234567890123 --temperature 24.5
python3 main.py ac-control --appliance-id 1234567890123 --fan strong
python3 main.py ac-control --appliance-id 1234567890123 --mode cool --temperature 24 --fan strong --batch

# 送信せず payload hex のみ確認
python3 main.py ac-control --appliance-id 1234567890123 --mode cool --temperature 24 --batch --print-payload
```

- `--mode`: `auto` / `cool` / `dry` / `heat` / `fan` / `smart_dry`
- `--temperature`: 16〜32 (0.5℃刻み)
- `--fan`: `auto` / `strong` / `mid` / `weak` / `mute`

## API/署名仕様（実装済み範囲）
- Host: `app.iolife.toshiba-lifestyle.com`
- Base path: `/v1/{endpoint}`
- 共通パラメータ:
  - `format=2`
  - `stamp=yyyyMMddHHmmss`
  - `language=ja_JP`（`--language` で変更可）
  - `appId=1203`
  - `src=203`
  - ログイン後は `sessionId`
- 署名:
  1. `path + sorted(params as k=v&...) + APP_KEY`
  2. SHA256小文字hex
  3. `sign` として送信
- ログイン時:
  - `password = SHA256(loginId + SHA256(rawPassword) + APP_KEY)`
  - `iampwd = SHA256(loginId + MD5(MD5(rawPassword)) + APP_KEY)`

## 解析メモ
- 本プロトコルは Midea AC UART プロトコルを Toshiba が拡張したもの(CRC8 テーブル・コマンドID・TLV 形式が一致)。詳細は `Iolife_API_SPEC.md` の「12. Protocol lineage」参照
- 状態応答 `0xC0` のバイト配置、温度の換算式、マルチプロパティの挙動は実機(RAS-G221E8P(W))で検証済み。`Iolife_API_SPEC.md` 11.5〜11.7 に記載
- 検証用スクリプト: `python3 tools/probe_ac.py --appliance-id <id>`(クエリのみ)

## トラブルシューティング
### `RuntimeError: pycryptodome is required` / `dataKey missing in session`
`Crypto` (pycryptodome) が無いとログイン時に `dataKey` を復号できず、
`session.json` の `dataKey` が `null` になります。その状態では
`order` を生成できません。

```bash
python3 -m pip install -r requirements.txt
```

Nix 環境などで pip が無い場合は、`PYTHONPATH` で pycryptodome を渡します。

```bash
export CRYPTO_PATH=$(nix build --no-link --print-out-paths nixpkgs#python3Packages.pycryptodome)
export PYTHONPATH="$CRYPTO_PATH/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}"
python3 main.py devices
```

(`python3.14` の部分は環境の Python バージョンに合わせてください。)
既に `session.json` がある場合は、`accessToken` から `dataKey` を復元できます。

```python
import main, json
p = "session.json"
s = json.load(open(p))
s["dataKey"] = main.decode_with_app_key(s["accessToken"], main.APP_KEY)
json.dump(s, open(p, "w"), ensure_ascii=False, indent=2)
```

### `invalidSession` / `errorCode=3106` が出る
セッション失効です。再ログインしてください。

```bash
rm -f session.json
python3 main.py login --account <email> --password <password>
python3 main.py devices
```

改善しない場合:
- 公式IoLIFEアプリを一度終了してから再実行
- `login` 直後に `ac-query` / `ac-power` を実行
- 実行ディレクトリが `main.py` と `session.json` のある場所か確認


```bash
python3 -m pip install -r requirements.txt
```

### `HTTP 504: Gateway Time-out`
API到達後に機器応答がタイムアウトしています。よくある原因:
- 機器オフライン
- `appliance-id` 違い
- ペイロード形式違い

