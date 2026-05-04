# ⚠️ このディレクトリは参照用です

ここを編集しても動作に反映されません。

実際に使われるのは Docker ベースイメージに
pip install された `acsl` パッケージです。

## ツールの書き方を知りたい場合

参考になるファイル:
- `acsl/tools/controller/pid.py` — PID コントローラの実装例
- `acsl/tools/sensor/direct_sensor.py` — センサの実装例
- `acsl/tools/base.py` — Tool Protocol の定義

## 自分のツールを作る場所

ワークスペースの `tools/` ディレクトリに作成してください:

```
workspace/
├── tools/            ← ここに書く
│   └── my_controller.py
├── config/           ← 設定はここ
│   └── rf_robot.yaml
└── common/           ← ここは読むだけ（このディレクトリ）
```

## 現在のバージョン

コンテナ内で確認:
```bash
pip show acsl-framework
```
