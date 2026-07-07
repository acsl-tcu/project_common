"""制御ループ向けノード実行ヘルパ (executor 選択 + GC 対策)。

40Hz 級の制御タイマーを持つ ROS2 ノードで、突発的な数十〜数百 ms の
ステップ停止を防ぐための定型をまとめたもの。project_drone2 の実機で
特定した 2 つの問題 (再現ベンチ付き) に対応する:

1. rclpy (jazzy) の MultiThreadedExecutor は購読トラフィックがあると
   busy-loop + タイマー飢餓を起こす。実測 (40Hz timer + 100Hz pub/sub):
     SingleThreadedExecutor : timer 間隔 p50=25.0ms max= 25ms CPU=  4%
     MultiThreaded(2)+購読  : timer 間隔 p50=72.4ms max=489ms CPU=104%
   スレッド数に関係なく発生し、既定ではさらに CPU コア数分のスレッドを
   生成する (32 コア機で 32 スレッド)。症状は「ノードプロセスが常時
   ~1 コア消費 + 制御ステップがランダムに数百 ms 停止」。

2. Python GC (世代2) はログ等でヒープが育つと停止が数百 ms まで成長する
   (8〜12 秒間隔・停止時間が単調増加が典型症状)。

使い方 (各プロジェクトの main()):

    from acsl.utils.realtime import spin

    def main(args=None):
        rclpy.init(args=args)
        node = MyNode()
        spin(node)      # setup_gc + executor 選択 + spin + destroy の定型
        rclpy.shutdown()

個別に使う場合:

    setup_gc(node.get_logger())
    executor = make_executor(node.get_logger())
    executor.add_node(node)
    executor.spin()

環境変数:
  ACSL_EXECUTOR=single (既定) | multi | multi:N
      multi にするのは「コールバックが長時間ブロックし並行実行が必須」の
      場合のみ。その場合も上記 busy-loop のリスクを理解した上で使うこと
      (ブロックする処理は独自スレッドに逃がして single にするのが推奨)。
  ACSL_GC_TUNING=1 (既定) | 0
      0 で GC 抑制のみ無効化 (停止時間の計測 warn ログは常に有効)。
"""

import gc
import logging
import os
import time

_GC_WARN_MS = 20.0


def _warn(logger, msg: str):
    """rclpy logger / 標準 logging のどちらでも warn を出す。"""
    if logger is None:
        logging.getLogger("acsl.realtime").warning(msg)
    elif hasattr(logger, "warn"):
        logger.warn(msg)
    else:
        logger.warning(msg)


def _info(logger, msg: str):
    if logger is None:
        logging.getLogger("acsl.realtime").info(msg)
    else:
        logger.info(msg)


def setup_gc(logger=None):
    """GC 停止の可視化と抑制。

    - 全 collection に callback を張り、20ms 超の停止を warn ログに出す
      (制御ステップの SLOW ログとの時刻照合で GC 起因かを確定できる)
    - gc.freeze() で起動時オブジェクト (ROS/numpy 等) を走査対象から外し、
      世代2 の発火閾値を 100 倍希釈して飛行/走行中の長時間停止を防ぐ
      (ACSL_GC_TUNING=0 で抑制のみ無効化、計測は常時有効)

    ノード生成が終わった後 (spin 直前) に一度だけ呼ぶこと。
    """
    t0 = {}

    def _cb(phase, info):
        gen = info.get("generation", -1)
        if phase == "start":
            t0[gen] = time.perf_counter()
        else:
            start = t0.pop(gen, None)
            if start is None:
                return
            ms = (time.perf_counter() - start) * 1e3
            if ms > _GC_WARN_MS:
                _warn(logger,
                      "GC pause: gen%d %.1fms (collected=%d) at wall=%s" % (
                          gen, ms, info.get("collected", -1),
                          time.strftime("%H:%M:%S", time.localtime()) +
                          ".%03d" % int((time.time() % 1) * 1000)))

    gc.callbacks.append(_cb)
    if os.environ.get("ACSL_GC_TUNING", "1") != "0":
        gc.collect()
        gc.freeze()
        # 既定 (700, 10, 10) → 世代2 の自動発火を 100 倍希釈。
        # 世代 0/1 は既定のまま (若いオブジェクトの回収は速い)。
        gc.set_threshold(700, 10, 1000)
        _info(logger, "GC tuning enabled: freeze + threshold(700,10,1000)")


def make_executor(logger=None):
    """executor を生成する。既定 SingleThreadedExecutor。

    ACSL_EXECUTOR=multi[:N] で MultiThreadedExecutor(num_threads=N, 既定2)。
    (rclpy jazzy の MTE は購読があると busy-loop するため、multi は
    ブロッキングコールバックの並行実行がどうしても必要な場合のみ。)
    """
    from rclpy.executors import (
        MultiThreadedExecutor,
        SingleThreadedExecutor,
    )
    mode = os.environ.get("ACSL_EXECUTOR", "single")
    if mode.startswith("multi"):
        n = int(mode.split(":", 1)[1]) if ":" in mode else 2
        executor = MultiThreadedExecutor(num_threads=n)
        _warn(logger,
              f"Executor: MultiThreadedExecutor({n}) — 購読があると "
              "busy-loop + タイマー飢餓のリスクあり (acsl.utils.realtime 参照)")
    else:
        executor = SingleThreadedExecutor()
        _info(logger, "Executor: SingleThreadedExecutor")
    return executor


def spin(node, gc_setup: bool = True):
    """setup_gc + executor 選択 + spin + destroy の定型一式。

    rclpy.init / rclpy.shutdown は呼び出し側で行う。
    """
    logger = node.get_logger() if hasattr(node, "get_logger") else None
    if gc_setup:
        setup_gc(logger)
    executor = make_executor(logger)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
