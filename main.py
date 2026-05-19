import signal
from app.game_app import LedgerHeistApp


def main() -> None:
    """Launch the Textual application."""
    # Ignore Ctrl+C (SIGINT) to prevent accidental program exits
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    LedgerHeistApp().run()


if __name__ == "__main__":
    main()
