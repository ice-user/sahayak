"""Chat with Sahayak in the terminal:  python -m sahayak.cli  [--show-tools]"""
import argparse

from .agent import Agent, default_trace_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-tools", action="store_true", help="print each tool call")
    args = ap.parse_args()

    agent = Agent(trace_dir=default_trace_dir())  # traces only with SAHAYAK_TRACES=1
    print("Sahayak - ask about government schemes in any language. Ctrl+C to quit.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not q:
            continue
        answer, trace = agent.chat(q)
        if args.show_tools:
            for s in trace.tool_calls():
                print(f"  [tool] {s['name']}({s['arguments']})")
        print(f"\nsahayak> {answer}\n")


if __name__ == "__main__":
    main()
