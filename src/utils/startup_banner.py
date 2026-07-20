from config import SETTINGS


# ANSI color codes for a bit of terminal flair.
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def log_startup_banner() -> None:
    """Print a banner showing the app name and the port it's running on."""
    name = SETTINGS.APP_NAME
    url = f"http://{SETTINGS.APP_HOST}:{SETTINGS.APP_PORT}"
    mode = "development" if SETTINGS.DEBUG else "production"

    line = "─" * 46
    banner = f"""
{_CYAN}╭{line}╮{_RESET}
{_CYAN}│{_RESET}  {_BOLD}{_GREEN}{name}{_RESET}
{_CYAN}│{_RESET}  {_DIM}is up and running{_RESET}
{_CYAN}│{_RESET}
{_CYAN}│{_RESET}  {_YELLOW}➜{_RESET}  Local:   {_BOLD}{url}{_RESET}
{_CYAN}│{_RESET}  {_YELLOW}➜{_RESET}  Docs:    {_BOLD}{url}/scalar{_RESET}
{_CYAN}│{_RESET}  {_YELLOW}➜{_RESET}  Mode:    {mode}
{_CYAN}╰{line}╯{_RESET}
"""
    print(banner)
