"""
main.py — Project entry point

Usage:
    python main.py                  # quick 4-combo simulation test
    python main.py --dashboard      # start the web dashboard
    python main.py --benchmark      # run all benchmarks, save CSVs
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def run_sim_test():
    """Quick smoke-test: run all 4 algorithm+policy combos and print summaries."""
    from sim.network import Router
    from sim.sender import Sender

    configs = [
        ("slow_start_aimd", "drop_tail"),
        ("slow_start_aimd", "red"),
        ("cubic",           "drop_tail"),
        ("cubic",           "red"),
    ]

    print(f"\n{'═'*55}")
    print("  Simulation smoke test (5000 packets each)")
    print(f"{'═'*55}")

    for algo, policy in configs:
        print(f"\n  ▶  {algo}  +  {policy}")
        router = Router(bandwidth_kbps=100, delay_ms=50,
                        queue_size=20, drop_policy=policy)
        sender = Sender(router, algorithm=algo)
        sender.run(num_packets=5000, verbose=False)
        print(sender.summary())
        print(router.summary())


def run_benchmark():
    from benchmarks.run_all import main as bench_main
    bench_main()


def run_dashboard():
    from dashboard.app import start
    start(host="127.0.0.1", port=8050, debug=False)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--dashboard" in args:
        run_dashboard()
    elif "--benchmark" in args:
        run_benchmark()
    else:
        run_sim_test()