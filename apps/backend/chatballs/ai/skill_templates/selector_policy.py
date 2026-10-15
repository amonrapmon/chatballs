"""Small positive selector grammar, including list counters used by the basis."""


def valid_selector(tokens, depth=0):
    if depth > 3:
        return False
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index else None
        after_colon = previous is not None and previous.type == "literal" and previous.value == ":"
        if after_colon and token.type == "ident" and token.value not in {"before", "after", "last-child"}:
            return False
        if token.type == "function":
            if not after_colon:
                return False
            if token.lower_name == "has":
                if not valid_selector(token.arguments, depth + 1):
                    return False
            elif token.lower_name == "nth-child":
                args = [part for part in token.arguments if part.type != "whitespace"]
                if len(args) != 1 or args[0].type != "number" or not args[0].is_integer or not 1 <= args[0].value <= 100:
                    return False
            else:
                return False
        elif token.type == "literal":
            if token.value not in {".", ">", ",", "*", ":", "~"}:
                return False
        elif token.type not in {"ident", "whitespace"}:
            return False
    return bool(tokens) and any(t.type == "ident" for t in tokens)
