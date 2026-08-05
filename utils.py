def safe_text(value):
    if value is None:
        return ""

    text = str(value)

    # remove broken emoji surrogate characters like \ud83d
    text = text.encode("utf-8", "ignore").decode("utf-8", "ignore")

    return text
