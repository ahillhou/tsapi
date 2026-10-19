def parse_command(message):
    message = message.strip()

    if not message:
        return None

    parts = message.upper().split()

    command = parts[0]

    target_extension = None

    if len(parts) > 1:
        target_extension = parts[1]

    return {
        "command": command,
        "target_extension": target_extension
    }