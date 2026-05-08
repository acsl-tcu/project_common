# project_common TODO

## Logger
- [ ] `Logger.from_rosbag(path)`: rosbag ファイルを Logger に読み込み、query API で統一的にアクセスする機能。外部トピック (VL, MAVROS2 等) と パイプライン内部データ (estimator/reference/controller) を同じ API で扱えるようにする。
