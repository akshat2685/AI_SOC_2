"""Safe command executor sandbox module."""
import re
from typing import List, Tuple, Set


class SafeCommandExecutor:
    """Validates commands and arguments against allowlists and traversal/injection rules."""

    ALLOWLIST: Set[str] = {
        "ping",
        "nslookup",
        "traceroute",
        "curl",
        "whois",
        "dig",
        "netstat",
    }

    # Shell metacharacters that could indicate command chaining or redirection
    BLOCKED_CHARS = re.compile(r"[;|><&`$()\{\}\\\r\n]")
    # Path traversal sequences
    PATH_TRAVERSAL = re.compile(r"(\.\./)|(\.\.\\)|(/\.\.)|(\\\.\.)")

    def validate_command(self, cmd: str, args: List[str]) -> Tuple[bool, str]:
        """Validate if a command and its arguments are safe for execution."""
        if cmd.lower() not in self.ALLOWLIST:
            return False, f"Command '{cmd}' is not in allowlist {sorted(self.ALLOWLIST)}"
        
        for arg in args:
            if not isinstance(arg, str):
                return False, f"Invalid argument type: {type(arg)}"
            
            if self.BLOCKED_CHARS.search(arg):
                return False, f"Argument contains blocked character (shell metacharacter): '{arg}'"
            
            if self.PATH_TRAVERSAL.search(arg):
                return False, f"Argument contains path traversal sequence: '{arg}'"
                
        return True, "Command valid and safe"


safe_executor = SafeCommandExecutor()
